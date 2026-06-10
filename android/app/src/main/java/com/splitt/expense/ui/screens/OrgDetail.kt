package com.splitt.expense.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material3.AlertDialog
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
import com.splitt.expense.network.EventRead
import com.splitt.expense.network.OrgMemberInviteRequest
import com.splitt.expense.ui.rootMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrgDetailRoute(
    orgId: Long,
    app: SplitExpenseApp,
    snackbar: SnackbarHostState,
    scope: CoroutineScope,
    onBack: () -> Unit,
    onEvent: (Long) -> Unit,
) {
    var title by remember { mutableStateOf("Organization") }
    var events by remember { mutableStateOf<List<EventRead>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showEvent by remember { mutableStateOf(false) }
    var newEventName by remember { mutableStateOf("") }
    var showInvite by remember { mutableStateOf(false) }
    var inviteMobile by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            try {
                val org = app.api.getOrganization(orgId)
                title = org.name
                events = app.api.listEvents(orgId)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(orgId) { reload() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showInvite = true }) {
                        Icon(Icons.Default.PersonAdd, contentDescription = "Invite member")
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showEvent = true }) {
                Icon(Icons.Default.Add, contentDescription = "New event")
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
            item {
                Text(
                    "Events",
                    Modifier.padding(12.dp),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            if (loading && events.isEmpty()) {
                item { Text("Loading…", Modifier.padding(16.dp)) }
            }
            items(events, key = { it.id }) { ev ->
                ListItem(
                    headlineContent = { Text(ev.name) },
                    supportingContent = { Text("Event #${ev.id}") },
                    modifier = Modifier.clickable { onEvent(ev.id) },
                )
            }
            if (!loading && events.isEmpty()) {
                item {
                    Text(
                        "No events yet. Tap + to add one.",
                        Modifier.padding(16.dp),
                    )
                }
            }
        }
    }

    if (showEvent) {
        AlertDialog(
            onDismissRequest = { showEvent = false },
            title = { Text("New event") },
            text = {
                OutlinedTextField(
                    newEventName,
                    { newEventName = it },
                    label = { Text("Event name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val n = newEventName.trim()
                        if (n.isEmpty()) return@TextButton
                        scope.launch {
                            try {
                                app.api.createEvent(orgId, mapOf("name" to n))
                                newEventName = ""
                                showEvent = false
                                reload()
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text("Create") }
            },
            dismissButton = {
                TextButton(onClick = { showEvent = false }) { Text("Cancel") }
            },
        )
    }

    if (showInvite) {
        AlertDialog(
            onDismissRequest = { showInvite = false },
            title = { Text("Invite to organization") },
            text = {
                OutlinedTextField(
                    inviteMobile,
                    { inviteMobile = it },
                    label = { Text("Member mobile") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val m = inviteMobile.trim()
                        if (m.length < 10) return@TextButton
                        scope.launch {
                            try {
                                app.api.inviteOrgMember(orgId, OrgMemberInviteRequest(m))
                                inviteMobile = ""
                                showInvite = false
                                snackbar.showSnackbar("Invitation sent (user must be registered).")
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text("Invite") }
            },
            dismissButton = {
                TextButton(onClick = { showInvite = false }) { Text("Cancel") }
            },
        )
    }
}
