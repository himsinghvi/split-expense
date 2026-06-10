package com.splitt.expense

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.Box
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.splitt.expense.ui.screens.EventDetailRoute
import com.splitt.expense.ui.screens.LoginRoute
import com.splitt.expense.ui.screens.OrgDetailRoute
import com.splitt.expense.ui.screens.OrgsRoute
import com.splitt.expense.ui.screens.RegisterRoute
import com.splitt.expense.ui.theme.SplitExpenseTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            SplitExpenseTheme {
                val app = applicationContext as SplitExpenseApp
                val snackbar = remember { SnackbarHostState() }
                val scope = rememberCoroutineScope()
                var ready by remember { mutableStateOf(false) }
                LaunchedEffect(Unit) {
                    app.session.loadFromDisk()
                    ready = true
                }
                if (!ready) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                } else {
                    val nav = rememberNavController()
                    val start = if (app.session.hasToken()) "orgs" else "login"
                    Scaffold(
                        snackbarHost = { SnackbarHost(snackbar) },
                    ) { padding ->
                        NavHost(
                            navController = nav,
                            startDestination = start,
                            modifier = Modifier.padding(padding),
                        ) {
                            composable("login") {
                                LoginRoute(
                                    app = app,
                                    snackbar = snackbar,
                                    scope = scope,
                                    onLoggedIn = {
                                        nav.navigate("orgs") {
                                            popUpTo("login") { inclusive = true }
                                        }
                                    },
                                    onRegister = { nav.navigate("register") },
                                )
                            }
                            composable("register") {
                                RegisterRoute(
                                    app = app,
                                    snackbar = snackbar,
                                    scope = scope,
                                    onDone = { nav.popBackStack() },
                                )
                            }
                            composable("orgs") {
                                OrgsRoute(
                                    app = app,
                                    snackbar = snackbar,
                                    scope = scope,
                                    onOrg = { id -> nav.navigate("org/$id") },
                                    onLogout = {
                                        scope.launch {
                                            app.session.clearToken()
                                            nav.navigate("login") {
                                                popUpTo(nav.graph.id) { inclusive = true }
                                                launchSingleTop = true
                                            }
                                        }
                                    },
                                )
                            }
                            composable("org/{orgId}") { entry ->
                                val orgId = entry.arguments?.getString("orgId")?.toLongOrNull() ?: return@composable
                                OrgDetailRoute(
                                    orgId = orgId,
                                    app = app,
                                    snackbar = snackbar,
                                    scope = scope,
                                    onBack = { nav.popBackStack() },
                                    onEvent = { eid -> nav.navigate("event/$eid") },
                                )
                            }
                            composable("event/{eventId}") { entry ->
                                val eventId = entry.arguments?.getString("eventId")?.toLongOrNull() ?: return@composable
                                EventDetailRoute(
                                    eventId = eventId,
                                    app = app,
                                    snackbar = snackbar,
                                    scope = scope,
                                    onBack = { nav.popBackStack() },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
