package com.splitt.expense.ui

import org.json.JSONArray
import org.json.JSONObject
import retrofit2.HttpException

fun HttpException.userMessage(): String {
    val raw = response()?.errorBody()?.use { it.string() } ?: return localizedMessage ?: "Request failed"
    return try {
        val obj = JSONObject(raw)
        when (val d = obj.opt("detail")) {
            is String -> d.ifBlank { raw }
            is JSONArray -> buildString {
                for (i in 0 until d.length()) {
                    val o = d.optJSONObject(i)
                    val msg = o?.optString("msg")?.takeIf { it.isNotBlank() }
                    if (msg != null) {
                        if (isNotEmpty()) append("\n")
                        append(msg)
                    }
                }
            }.ifBlank { raw }
            else -> raw
        }
    } catch (_: Exception) {
        raw
    }
}

fun Throwable.rootMessage(): String = when (this) {
    is HttpException -> userMessage()
    else -> localizedMessage ?: message ?: toString()
}
