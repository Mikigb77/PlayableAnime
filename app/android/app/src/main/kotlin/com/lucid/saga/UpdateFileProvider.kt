package com.lucid.saga

import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.File
import java.io.FileNotFoundException

/**
 * Lends a downloaded update to Android's installer (S12, MainActivity.kt), read-only. It isn't
 * exported: only an app this one grants a link to, for one install, can read it, and only the APKs
 * in the updates folder of the app's cache, by name.
 */
class UpdateFileProvider : ContentProvider() {
    override fun onCreate(): Boolean = true

    override fun getType(uri: Uri): String = APK_TYPE

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        if (mode != "r") throw SecurityException("updates are read-only")
        val file = fileFor(uri) ?: throw FileNotFoundException("no such update")
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    }

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?,
    ): Cursor? {
        val file = fileFor(uri) ?: return null
        val columns = projection ?: arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)
        val row = columns.map { column ->
            when (column) {
                OpenableColumns.DISPLAY_NAME -> file.name
                OpenableColumns.SIZE -> file.length()
                else -> null
            }
        }
        return MatrixCursor(columns, 1).apply { addRow(row) }
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? =
        throw UnsupportedOperationException("read-only")

    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?,
    ): Int = throw UnsupportedOperationException("read-only")

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int =
        throw UnsupportedOperationException("read-only")

    private fun fileFor(uri: Uri): File? {
        val context = context ?: return null
        val name = uri.pathSegments.singleOrNull() ?: return null
        if (uri.authority != authority(context) || !serves(name)) return null
        return File(folder(context), name).takeIf { it.isFile }
    }

    companion object {
        const val APK_TYPE = "application/vnd.android.package-archive"

        private val NAME = Regex("lucid-saga-[0-9]+\\.apk")

        /** Where Dart downloads updates: the app's cache, which Android may clear. */
        fun folder(context: Context): File = File(context.cacheDir, "updates")

        /** Whether [name] is a downloaded update's file name. */
        fun serves(name: String): Boolean = NAME.matches(name)

        fun uriFor(context: Context, file: File): Uri = Uri.Builder()
            .scheme("content")
            .authority(authority(context))
            .appendPath(file.name)
            .build()

        private fun authority(context: Context) = "${context.packageName}.updates"
    }
}
