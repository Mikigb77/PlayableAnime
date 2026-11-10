package com.lucid.saga

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.DigestInputStream
import java.security.MessageDigest
import java.util.concurrent.Executors

/**
 * The app's own updates (S12, lib/features/update/app_update.dart). Dart downloads the newer APK
 * into the cache; this checks it and opens Android's own installer on it, through
 * [UpdateFileProvider], which lets only that installer read the file. The installer stays in front
 * for the whole update: it asks the player (and, the first time, to allow installs from Lucid
 * Saga), lets Google Play Protect check the build, installs it, which ends this app, and then says
 * "App installed" with Open, which starts the new build. So the player goes from Install to the new
 * version without hunting for the app, and nothing depends on this app staying alive. Only the APK
 * from the GitHub release calls this: a Google Play build leaves updates to Play.
 */
class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "info" -> result.success(info())
                    "unmetered" -> result.success(unmetered())
                    "install" -> install(
                        call.argument<String>("path"),
                        call.argument<String>("sha256"),
                        result,
                    )
                    else -> result.notImplemented()
                }
            }
        }
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // Android's installer closed and this app is still running: the player said no, or Android
    // couldn't install it and said why on its own screen. An install that worked ends the app first.
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_INSTALL) channel?.invokeMethod("installerClosed", null)
    }

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
            "updates_dir" to UpdateFileProvider.folder(this).absolutePath,
        )
    }

    /** Whether the network isn't metered (Wi-Fi), so a newer build may be fetched unasked. */
    private fun unmetered(): Boolean {
        val connectivity =
            getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        return try {
            !connectivity.isActiveNetworkMetered
        } catch (e: SecurityException) {
            false
        }
    }

    private fun install(path: String?, sha256: String?, result: MethodChannel.Result) {
        if (path == null || sha256 == null) {
            result.error("failed", "path and sha256 are required", null)
            return
        }
        worker.execute {
            try {
                val file = File(path).canonicalFile
                if (file.parentFile != UpdateFileProvider.folder(this).canonicalFile ||
                    !file.isFile ||
                    !UpdateFileProvider.serves(file.name)
                ) {
                    throw InstallFailed("failed", "not a downloaded update")
                }
                if (!sha256Of(file).equals(sha256, ignoreCase = true)) {
                    file.delete()
                    throw InstallFailed("checksum", "the download isn't the published build")
                }
                main.post { openInstaller(file, result) }
            } catch (e: InstallFailed) {
                main.post { result.error(e.code, e.message, null) }
            } catch (e: Exception) {
                main.post { result.error("failed", e.javaClass.simpleName, null) }
            }
        }
    }

    /**
     * Opens Android's installer in this app's task, so its result comes back here if it closes
     * while the app still runs. When the install replaces the app, Android ends the app's own
     * screens only, and the installer's "App installed" with Open stays.
     */
    private fun openInstaller(file: File, result: MethodChannel.Result) {
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(UpdateFileProvider.uriFor(this, file), UpdateFileProvider.APK_TYPE)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        try {
            startActivityForResult(intent, REQUEST_INSTALL)
            result.success(null)
        } catch (e: ActivityNotFoundException) {
            result.error("failed", "no installer", null)
        } catch (e: SecurityException) {
            result.error("failed", "installer refused", null)
        }
    }

    private fun sha256Of(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        DigestInputStream(file.inputStream(), digest).use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (input.read(buffer) != -1) {
                // Reading is enough: the stream feeds the digest.
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private class InstallFailed(val code: String, message: String) : Exception(message)

    private companion object {
        const val CHANNEL = "lucid_saga/app_update"
        const val REQUEST_INSTALL = 0x5a6a
    }
}
