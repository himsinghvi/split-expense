package com.splitt.expense.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.splitt.expense.SplitExpenseApp
import com.splitt.expense.network.OrganizationRead
import com.splitt.expense.network.UserMe
import com.splitt.expense.ui.rootMessage
import com.splitt.expense.util.formatInr
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrgsRoute(
    app: SplitExpenseApp,
    snackbar: SnackbarHostState,
    scope: CoroutineScope,
    onOrg: (Long) -> Unit,
    onLogout: () -> Unit,
) {
    var items by remember { mutableStateOf<List<OrganizationRead>>(emptyList()) }
    var me by remember { mutableStateOf<UserMe?>(null) }
    var loading by remember { mutableStateOf(true) }
    var showCreate by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            try {
                me = app.api.me()
                items = app.api.organizations()
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(Unit) { reload() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Organizations") },
                actions = {
                    IconButton(onClick = onLogout) {
                        Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = "Sign out")
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showCreate = true }) {
                Icon(Icons.Default.Add, contentDescription = "Add organization")
            }
        },
    ) { padding ->
        LazyColumn(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            if (loading && items.isEmpty()) {
                item { Text("Loading…", Modifier.padding(16.dp)) }
            }
            me?.let { u ->
                item {
                    Card(
                        Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 8.dp, vertical = 8.dp),
                        colors = CardDefaults.cardColors(),
                    ) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Your totals (all events)", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "Only counts event members linked to your account.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text("You pooled: ${formatInr(u.totalContributed)}")
                            Text("You spent (share): ${formatInr(u.totalExpended)}")
                            Text("You have left: ${formatInr(u.totalRemaining)}")
                        }
                    }
                }
            }
            items(items, key = { it.id }) { org ->
                ListItem(
                    headlineContent = { Text(org.name) },
                    supportingContent = { Text("Tap to open") },
                    modifier = Modifier.clickable { onOrg(org.id) },
                )
            }
            if (!loading && items.isEmpty()) {
                item {
                    Text(
                        "No organizations yet. Tap + to create one.",
                        Modifier.padding(16.dp),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                }
            }
        }
    }

    if (showCreate) {
        AlertDialog(
            onDismissRequest = { showCreate = false },
            title = { Text("New organization") },
            text = {
                OutlinedTextField(
                    newName,
                    { newName = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val n = newName.trim()
                        if (n.isEmpty()) return@TextButton
                        scope.launch {
                            try {
                                app.api.createOrganization(mapOf("name" to n))
                                newName = ""
                                showCreate = false
                                reload()
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text("Create") }
            },
            dismissButton = {
                TextButton(onClick = { showCreate = false }) { Text("Cancel") }
            },
        )
    }
}
