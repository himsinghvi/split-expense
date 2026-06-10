package com.splitt.expense.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.splitt.expense.SplitExpenseApp
import com.splitt.expense.network.UserLoginRequest
import com.splitt.expense.network.UserRegisterRequest
import com.splitt.expense.ui.rootMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.material3.SnackbarHostState

@Composable
fun LoginRoute(
    app: SplitExpenseApp,
    snackbar: SnackbarHostState,
    scope: CoroutineScope,
    onLoggedIn: () -> Unit,
    onRegister: () -> Unit,
) {
    var mobile by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Sign in", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(
            mobile,
            { mobile = it },
            label = { Text("Mobile") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            password,
            { password = it },
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                if (busy) return@Button
                busy = true
                scope.launch {
                    try {
                        val t = app.api.login(UserLoginRequest(mobile.trim(), password))
                        app.session.saveToken(t.accessToken)
                        onLoggedIn()
                    } catch (e: Exception) {
                        snackbar.showSnackbar(e.rootMessage())
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && mobile.isNotBlank() && password.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Signing in…" else "Sign in")
        }
        OutlinedButton(onClick = onRegister, modifier = Modifier.fillMaxWidth()) {
            Text("Create account")
        }
    }
}

@Composable
fun RegisterRoute(
    app: SplitExpenseApp,
    snackbar: SnackbarHostState,
    scope: CoroutineScope,
    onDone: () -> Unit,
) {
    var fullName by remember { mutableStateOf("") }
    var mobile by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Register", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(
            fullName,
            { fullName = it },
            label = { Text("Full name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            mobile,
            { mobile = it },
            label = { Text("Mobile") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            password,
            { password = it },
            label = { Text("Password (min 6)") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                if (busy) return@Button
                busy = true
                scope.launch {
                    try {
                        app.api.register(
                            UserRegisterRequest(
                                mobile = mobile.trim(),
                                password = password,
                                fullName = fullName.trim(),
                            ),
                        )
                        snackbar.showSnackbar("Account created. Please sign in.")
                        onDone()
                    } catch (e: Exception) {
                        snackbar.showSnackbar(e.rootMessage())
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy && fullName.isNotBlank() && mobile.isNotBlank() && password.length >= 6,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Please wait…" else "Register")
        }
    }
}
