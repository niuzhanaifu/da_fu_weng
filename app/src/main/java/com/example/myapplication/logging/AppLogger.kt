package com.example.myapplication.logging

import android.content.Context
import android.os.Build
import android.util.Log
import java.io.BufferedWriter
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object AppLogger {
    private const val MAX_LOG_FILES = 10
    private const val CURRENT_LOG_NAME = "debug-00.log"

    private val lock = Any()
    private val lineTimeFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    private var initialized = false
    private var writer: BufferedWriter? = null
    private var logsDir: File? = null
    private var previousCrashHandler: Thread.UncaughtExceptionHandler? = null

    fun install(context: Context) {
        synchronized(lock) {
            if (initialized) return

            val dir = File(context.filesDir, "logs").apply { mkdirs() }
            logsDir = dir
            rotateLogs()
            writer = File(dir, CURRENT_LOG_NAME).outputStream().bufferedWriter(Charsets.UTF_8)
            initialized = true
            previousCrashHandler = Thread.getDefaultUncaughtExceptionHandler()
            Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
                e("Crash", "Uncaught exception on ${thread.name}", throwable)
                writer?.flush()
                previousCrashHandler?.uncaughtException(thread, throwable)
            }
            i("AppLogger", "Logger started. dir=${logsDir?.absolutePath}")
            i("Device", "android=${Build.VERSION.RELEASE}, sdk=${Build.VERSION.SDK_INT}, model=${Build.MANUFACTURER} ${Build.MODEL}")
        }
    }

    fun logDirectoryPath(): String = logsDir?.absolutePath.orEmpty()

    fun clearLocalData(context: Context) {
        synchronized(lock) {
            writer?.flush()
            writer?.close()
            writer = null

            context.cacheDir.deleteRecursively()
            File(context.filesDir, "logs").deleteRecursively()

            val dir = File(context.filesDir, "logs").apply { mkdirs() }
            logsDir = dir
            writer = File(dir, CURRENT_LOG_NAME).outputStream().bufferedWriter(Charsets.UTF_8)
            initialized = true
            i("AppLogger", "Local logs and cache cleared. dir=${dir.absolutePath}")
        }
    }

    fun d(tag: String, message: String) {
        Log.d(tag, message)
        write("DEBUG", tag, message, null)
    }

    fun i(tag: String, message: String) {
        Log.i(tag, message)
        write("INFO", tag, message, null)
    }

    fun w(tag: String, message: String, throwable: Throwable? = null) {
        Log.w(tag, message, throwable)
        write("WARN", tag, message, throwable)
    }

    fun e(tag: String, message: String, throwable: Throwable? = null) {
        Log.e(tag, message, throwable)
        write("ERROR", tag, message, throwable)
    }

    private fun rotateLogs() {
        val dir = logsDir ?: return
        File(dir, "debug-${(MAX_LOG_FILES - 1).toString().padStart(2, '0')}.log").delete()
        for (index in MAX_LOG_FILES - 2 downTo 0) {
            val source = File(dir, "debug-${index.toString().padStart(2, '0')}.log")
            if (source.exists()) {
                val target = File(dir, "debug-${(index + 1).toString().padStart(2, '0')}.log")
                source.renameTo(target)
            }
        }
    }

    private fun write(level: String, tag: String, message: String, throwable: Throwable?) {
        synchronized(lock) {
            if (!initialized) return
            val time = lineTimeFormat.format(Date())
            val thread = Thread.currentThread().name
            writer?.apply {
                append(time)
                append(" ")
                append(level)
                append("/")
                append(tag)
                append(" [")
                append(thread)
                append("] ")
                append(message)
                newLine()
                throwable?.stackTraceToString()?.lineSequence()?.forEach {
                    append("    ")
                    append(it)
                    newLine()
                }
                flush()
            }
        }
    }
}
