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
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
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
import androidx.compose.material3.menuAnchor
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
import com.splitt.expense.network.MemberBalanceRead
import com.splitt.expense.network.OrgMemberInviteRequest
import com.splitt.expense.network.OrgPoolContributionCreateRequest
import com.splitt.expense.ui.rootMessage
import com.splitt.expense.util.formatInr
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.math.RoundingMode

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
    var poolAvailable by remember { mutableStateOf<Double?>(null) }
    var poolContributed by remember { mutableStateOf<Double?>(null) }
    var poolExpenses by remember { mutableStateOf<Double?>(null) }
    var orgBalances by remember { mutableStateOf<List<MemberBalanceRead>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var showEvent by remember { mutableStateOf(false) }
    var newEventName by remember { mutableStateOf("") }
    var showInvite by remember { mutableStateOf(false) }
    var inviteMobile by remember { mutableStateOf("") }

    var showAddPool by remember { mutableStateOf(false) }
    var poolPickExpanded by remember { mutableStateOf(false) }
    var poolPickUserId by remember { mutableStateOf<Long?>(null) }
    var poolAmountStr by remember { mutableStateOf("") }
    var poolNoteStr by remember { mutableStateOf("") }

    fun reload() {
        scope.launch {
            loading = true
            try {
                val org = app.api.getOrganization(orgId)
                title = org.name
                poolAvailable = org.poolAvailable
                poolContributed = org.poolTotalContributed
                poolExpenses = org.poolTotalExpenses
                events = app.api.listEvents(orgId)
                orgBalances = app.api.orgBalances(orgId)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(orgId) { reload() }

    val poolRoster = remember(orgBalances) {
        orgBalances.mapNotNull { b ->
            b.userId?.let { uid -> uid to b.name }
        }.distinctBy { it.first }
    }

    LaunchedEffect(showAddPool, poolRoster) {
        if (showAddPool && poolPickUserId == null && poolRoster.isNotEmpty()) {
            poolPickUserId = poolRoster.first().first
        }
    }

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
                    IconButton(
                        onClick = {
                            poolPickUserId = poolRoster.firstOrNull()?.first
                            poolAmountStr = ""
                            poolNoteStr = ""
                            poolPickExpanded = false
                            showAddPool = true
                        },
                        enabled = poolRoster.isNotEmpty(),
                    ) {
                        Icon(Icons.Default.AccountBalance, contentDescription = "Add pool money")
                    }
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
                val p = poolAvailable
                val c = poolContributed
                val s = poolExpenses
                if (p != null || c != null || s != null) {
                    Text(
                        buildString {
                            if (p != null) append("Pool available: ${formatInr(BigDecimal.valueOf(p))}")
                            if (c != null) append(" · Contributed: ${formatInr(BigDecimal.valueOf(c))}")
                            if (s != null) append(" · Spent (org): ${formatInr(BigDecimal.valueOf(s))}")
                        },
                        Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            item {
                Text(
                    "Member balances (org-wide)",
                    Modifier.padding(12.dp),
                    style = MaterialTheme.typography.titleSmall,
                )
            }
            items(orgBalances, key = { it.memberId }) { b ->
                ListItem(
                    headlineContent = { Text(b.name) },
                    supportingContent = {
                        Text(
                            "In: ${formatInr(b.contributed)} · Out: ${formatInr(b.expended)} · Left: ${formatInr(b.remaining)}",
                        )
                    },
                )
            }
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

    if (showAddPool) {
        AlertDialog(
            onDismissRequest = {
                showAddPool = false
                poolPickExpanded = false
            },
            title = { Text("Add to organization pool") },
            text = {
                if (poolRoster.isEmpty()) {
                    Text("Add people to this organization first (invite by mobile), then you can log pool deposits for them.")
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        ExposedDropdownMenuBox(
                            expanded = poolPickExpanded,
                            onExpandedChange = { poolPickExpanded = !poolPickExpanded },
                        ) {
                            OutlinedTextField(
                                value = poolRoster.find { it.first == poolPickUserId }?.second ?: "",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Member") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = poolPickExpanded) },
                                modifier = Modifier
                                    .menuAnchor()
                                    .fillMaxWidth(),
                            )
                            ExposedDropdownMenu(
                                expanded = poolPickExpanded,
                                onDismissRequest = { poolPickExpanded = false },
                            ) {
                                poolRoster.forEach { (uid, name) ->
                                    DropdownMenuItem(
                                        text = { Text(name) },
                                        onClick = {
                                            poolPickUserId = uid
                                            poolPickExpanded = false
                                        },
                                    )
                                }
                            }
                        }
                        OutlinedTextField(
                            poolAmountStr,
                            { poolAmountStr = it },
                            label = { Text("Amount (₹)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            poolNoteStr,
                            { poolNoteStr = it },
                            label = { Text("Note (optional)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (poolRoster.isEmpty()) {
                            showAddPool = false
                            return@TextButton
                        }
                        val uid = poolPickUserId ?: return@TextButton
                        val amt = try {
                            BigDecimal(poolAmountStr.trim()).setScale(2, RoundingMode.HALF_UP)
                        } catch (_: Exception) {
                            scope.launch { snackbar.showSnackbar("Invalid amount") }
                            return@TextButton
                        }
                        if (amt <= BigDecimal.ZERO) {
                            scope.launch { snackbar.showSnackbar("Amount must be positive") }
                            return@TextButton
                        }
                        scope.launch {
                            try {
                                app.api.addOrgContribution(
                                    orgId,
                                    OrgPoolContributionCreateRequest(
                                        userId = uid,
                                        amount = amt,
                                        note = poolNoteStr.trim().ifBlank { null },
                                    ),
                                )
                                poolAmountStr = ""
                                poolNoteStr = ""
                                showAddPool = false
                                reload()
                                snackbar.showSnackbar("Pool entry added.")
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text(if (poolRoster.isEmpty()) "OK" else "Save") }
            },
            dismissButton = {
                TextButton(onClick = { showAddPool = false }) { Text("Cancel") }
            },
        )
    }
}
