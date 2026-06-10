package com.splitt.expense

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "session")

class SessionStore(private val context: Context) {
    private val keyToken = stringPreferencesKey("jwt")

    @Volatile
    var bearerToken: String? = null
        private set

    fun hasToken(): Boolean = !bearerToken.isNullOrBlank()

    suspend fun loadFromDisk() {
        val t = context.dataStore.data.map { it[keyToken] }.first()
        bearerToken = t
    }

    suspend fun saveToken(token: String) {
        context.dataStore.edit { it[keyToken] = token }
        bearerToken = token
    }

    suspend fun clearToken() {
        context.dataStore.edit { it.remove(keyToken) }
        bearerToken = null
    }
}
