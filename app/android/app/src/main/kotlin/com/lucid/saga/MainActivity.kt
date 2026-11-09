package com.lucid.saga

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.DigestInputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * The app's own updates (S12, lib/features/update/app_update.dart). Dart downloads the newer APK
 * into the cache; this hands it to Android through a PackageInstaller session, so the file is
 * never shared with another app. Android asks the player to confirm (and, the first time, to allow
 * installs from Lucid Saga), then replaces the app. Once Android starts installing, Dart covers the
 * app with "Updating Lucid Saga" and keeps it in front: Android and Google Play Protect may still
 * check the build or ask the player before the new build is in place, and an app that leaves the
 * screen then can leave the install stalled. Android ends the app when it replaces it. Only the APK
 * from the GitHub release calls this: a Google Play build leaves updates to Play.
 */
class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    private var receiver: BroadcastReceiver? = null
    private var watcher: PackageInstaller.SessionCallback? = null

    // Whether this screen can be seen, so Android lets it open the installer's question.
    private var visible = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "info" -> result.success(info())
                    "install" -> install(
                        call.argument<String>("path"),
                        call.argument<String>("sha256"),
                        result,
                    )
                    else -> result.notImplemented()
                }
            }
        }
        // A screen rebuilt while Android asks the player still hears how it ends.
        if (waiting.isNotEmpty() || installing != NONE) listenForStatus()
    }

    override fun onStart() {
        super.onStart()
        visible = true
    }

    // The question came from the system's installer, with our token (onStatus).
    @SuppressLint("UnsafeIntentLaunch")
    override fun onResume() {
        super.onResume()
        // A question that came while the app was out of sight shows now, unless it was dropped.
        val (sessionId, confirm) = question ?: return
        question = null
        if (sessionId in waiting) startActivity(confirm)
    }

    override fun onStop() {
        visible = false
        super.onStop()
    }

    override fun onDestroy() {
        receiver?.let { unregisterReceiver(it) }
        receiver = null
        watcher?.let { packageManager.packageInstaller.unregisterSessionCallback(it) }
        watcher = null
        worker.shutdown()
        super.onDestroy()
    }

    private fun updatesDir(): File = File(cacheDir, "updates")

    private fun info(): Map<String, Any> {
        val pkg = if (Build.VERSION.SDK_INT >= 33) {
            packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(0))
        } else {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0)
        }
        val build = if (Build.VERSION.SDK_INT >= 28) {
            pkg.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            pkg.versionCode.toLong()
        }
        return mapOf(
            "build" to build,
            "version" to (pkg.versionName ?: ""),
            "updates_dir" to updatesDir().absolutePath,
        )
    }

    private fun install(path: String?, sha256: String?, result: MethodChannel.Result) {
        if (path == null || sha256 == null) {
            result.error("failed", "path and sha256 are required", null)
            return
        }
        // Dart asks again only once no install is going on, or after one failed unheard.
        installing = NONE
        listenForStatus()
        worker.execute {
            try {
                val file = File(path).canonicalFile
                if (file.parentFile != updatesDir().canonicalFile || !file.isFile) {
                    throw InstallFailed("failed", "not a downloaded update")
                }
                commit(file, sha256)
                main.post { result.success(null) }
            } catch (e: InstallFailed) {
                main.post { result.error(e.code, e.message, null) }
            } catch (e: Exception) {
                main.post { result.error("failed", e.javaClass.simpleName, null) }
            }
        }
    }

    /** Copies the APK into a new session while checking its SHA-256, then commits it. */
    private fun commit(file: File, sha256: String) {
        val installer = packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(packageName)
        params.setSize(file.length())
        if (Build.VERSION.SDK_INT >= 31) {
            // Android 12 and later may skip the question once this app installed itself before.
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        }
        val sessionId = installer.createSession(params)
        val session = installer.openSession(sessionId)
        waiting.add(sessionId)
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            session.openWrite("base.apk", 0, file.length()).use { out ->
                DigestInputStream(file.inputStream(), digest).use { it.copyTo(out) }
                session.fsync(out)
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (!actual.equals(sha256, ignoreCase = true)) {
                file.delete()
                throw InstallFailed("checksum", "the download isn't the published build")
            }
            val status = Intent(ACTION_STATUS).setPackage(packageName).putExtra(EXTRA_TOKEN, token)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
            val pending = PendingIntent.getBroadcast(this, sessionId, status, flags)
            session.commit(pending.intentSender)
            session.close()
        } catch (e: Exception) {
            waiting.remove(sessionId)
            session.abandon()
            throw e
        }
    }

    // Before Android 13 there is no flag to keep it private; the token guards it there.
    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    private fun listenForStatus() {
        if (watcher == null) {
            val callback = SessionProgress()
            packageManager.packageInstaller.registerSessionCallback(callback, main)
            watcher = callback
        }
        if (receiver != null) return
        val listener = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) = onStatus(intent)
        }
        val filter = IntentFilter(ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(listener, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(listener, filter)
        }
        receiver = listener
    }

    // The confirmation comes from the system's installer, through the PendingIntent above: the
    // token proves it, so launching it is safe.
    @SuppressLint("UnsafeIntentLaunch")
    private fun onStatus(intent: Intent) {
        if (intent.getStringExtra(EXTRA_TOKEN) != token) return
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, NONE)
                if (installing != NONE && sessionId != installing) {
                    // Android is already installing a build the player said yes to: no need to
                    // ask about the same one again. The one installing is never dropped.
                    abandonQuietly(sessionId)
                    return
                }
                val confirm = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                }
                when {
                    confirm == null -> report("failed")
                    // Android opens it only from an app that can be seen; otherwise it waits.
                    visible -> {
                        question = null
                        startActivity(confirm)
                    }
                    else -> question = sessionId to confirm
                }
            }
            PackageInstaller.STATUS_SUCCESS -> report("installed")
            PackageInstaller.STATUS_FAILURE_ABORTED -> report("cancelled")
            else -> report("failed")
        }
    }

    private fun report(status: String) {
        channel?.invokeMethod("installStatus", mapOf("status" to status))
    }

    /**
     * Tells Dart when Android starts installing one of our sessions: after the player said yes, or
     * at once when nothing needed asking. Android counts copying the APK in as the first 80% of a
     * session's progress (every version since PackageInstaller came in, Android 5), and goes past
     * it only once nothing stands in the way of the install.
     */
    private inner class SessionProgress : PackageInstaller.SessionCallback() {
        override fun onCreated(sessionId: Int) = Unit

        override fun onBadgingChanged(sessionId: Int) = Unit

        override fun onActiveChanged(sessionId: Int, active: Boolean) = Unit

        override fun onProgressChanged(sessionId: Int, progress: Float) {
            if (progress <= PAST_COPY || !waiting.remove(sessionId)) return
            installing = sessionId
            // A question the player asked again would install the same build a second time.
            waiting.toList().forEach { abandonQuietly(it) }
            report("started")
        }

        override fun onFinished(sessionId: Int, success: Boolean) {
            waiting.remove(sessionId)
            if (sessionId == installing) installing = NONE
        }
    }

    private fun abandonQuietly(sessionId: Int) {
        waiting.remove(sessionId)
        if (question?.first == sessionId) question = null
        try {
            packageManager.packageInstaller.abandonSession(sessionId)
        } catch (e: Exception) {
            // Already finished, so nothing is left to abandon.
        }
    }

    private class InstallFailed(val code: String, message: String) : Exception(message)

    private companion object {
        const val CHANNEL = "lucid_saga/app_update"
        const val ACTION_STATUS = "com.lucid.saga.UPDATE_STATUS"
        const val EXTRA_TOKEN = "com.lucid.saga.UPDATE_TOKEN"
        const val NONE = -1

        // Just past the 0.8 that a committed session reports while it waits for the player.
        const val PAST_COPY = 0.85f

        // These belong to the process, not the screen, which Android may rebuild while it asks
        // the player.

        // Only status intents carrying this came from our own PendingIntent, through the installer.
        val token: String = UUID.randomUUID().toString()

        // Our sessions that Android hasn't started installing yet.
        val waiting: MutableSet<Int> = ConcurrentHashMap.newKeySet()

        // The session Android is installing, or NONE.
        @Volatile var installing = NONE

        // Android's question for a session, kept while the app was out of sight.
        @Volatile var question: Pair<Int, Intent>? = null
    }
}
