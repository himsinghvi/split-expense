package com.splitt.expense.ui.screens

import android.content.Intent
import android.os.Environment
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.splitt.expense.SplitExpenseApp
import com.splitt.expense.network.ExpenseCreateRequest
import com.splitt.expense.network.ExpenseRead
import com.splitt.expense.network.MemberBalanceRead
import com.splitt.expense.network.MemberCreateRequest
import com.splitt.expense.network.MemberRead
import com.splitt.expense.network.ExpenseSplitInputDto
import com.splitt.expense.ui.rootMessage
import com.splitt.expense.util.equalSplitRows
import com.splitt.expense.util.formatInr
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventDetailRoute(
    eventId: Long,
    app: SplitExpenseApp,
    snackbar: SnackbarHostState,
    scope: CoroutineScope,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    var tab by remember { mutableIntStateOf(0) }
    var title by remember { mutableStateOf("Event") }
    var orgPoolAvailable by remember { mutableStateOf<Double?>(null) }
    var members by remember { mutableStateOf<List<MemberRead>>(emptyList()) }
    var expenses by remember { mutableStateOf<List<ExpenseRead>>(emptyList()) }
    var balances by remember { mutableStateOf<List<MemberBalanceRead>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    var showMember by remember { mutableStateOf(false) }
    var newMemberName by remember { mutableStateOf("") }
    var newMemberMobile by remember { mutableStateOf("") }

    var showExpense by remember { mutableStateOf(false) }
    var expTitle by remember { mutableStateOf("") }
    var expCategory by remember { mutableStateOf("General") }
    var expTotal by remember { mutableStateOf("") }
    var expDate by remember { mutableStateOf(LocalDate.now().toString()) }
    var expEqualSplit by remember { mutableStateOf(true) }
    val expInclude = remember { mutableStateMapOf<Long, Boolean>() }
    val expCustomAmounts = remember { mutableStateMapOf<Long, String>() }

    fun reloadMembers() {
        scope.launch {
            try {
                val m = app.api.members(eventId)
                members = m
                m.forEach { member ->
                    if (!expInclude.containsKey(member.id)) expInclude[member.id] = true
                    if (!expCustomAmounts.containsKey(member.id)) expCustomAmounts[member.id] = ""
                }
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            }
        }
    }

    fun reloadExpenses() {
        scope.launch {
            try {
                expenses = app.api.expenses(eventId)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            }
        }
    }

    fun reloadBalances() {
        scope.launch {
            try {
                balances = app.api.balances(eventId)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            }
        }
    }

    fun reloadAll() {
        scope.launch {
            loading = true
            try {
                val ev = app.api.getEvent(eventId)
                title = ev.name
                orgPoolAvailable = ev.organizationPoolAvailable
                val m = app.api.members(eventId)
                members = m
                m.forEach { member ->
                    if (!expInclude.containsKey(member.id)) expInclude[member.id] = true
                    if (!expCustomAmounts.containsKey(member.id)) expCustomAmounts[member.id] = ""
                }
                expenses = app.api.expenses(eventId)
                balances = app.api.balances(eventId)
            } catch (e: Exception) {
                snackbar.showSnackbar(e.rootMessage())
            } finally {
                loading = false
            }
        }
    }

    LaunchedEffect(eventId) { reloadAll() }

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
                            scope.launch {
                                try {
                                    val file = withContext(Dispatchers.IO) {
                                        app.api.exportXlsx(eventId).use { body ->
                                            val dir =
                                                context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                                                    ?: context.filesDir
                                            val f = File(dir, "event_${eventId}_export.xlsx")
                                            body.byteStream().use { input ->
                                                f.outputStream().use { output -> input.copyTo(output) }
                                            }
                                            f
                                        }
                                    }
                                    val uri = FileProvider.getUriForFile(
                                        context,
                                        "${context.packageName}.fileprovider",
                                        file,
                                    )
                                    val intent = Intent(Intent.ACTION_VIEW).apply {
                                        setDataAndType(
                                            uri,
                                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        )
                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                    }
                                    context.startActivity(Intent.createChooser(intent, "Open Excel"))
                                } catch (e: Exception) {
                                    snackbar.showSnackbar(e.rootMessage())
                                }
                            }
                        },
                    ) {
                        Icon(Icons.Default.FileDownload, contentDescription = "Export Excel")
                    }
                },
            )
        },
        floatingActionButton = {
            if (tab == 0 || tab == 1) {
                FloatingActionButton(
                    onClick = {
                        when (tab) {
                            0 -> showMember = true
                            1 -> showExpense = true
                        }
                    },
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Add")
                }
            }
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            PrimaryTabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Members") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Expenses") })
                Tab(selected = tab == 2, onClick = { tab = 2 }, text = { Text("Org pool") })
                Tab(selected = tab == 3, onClick = { tab = 3 }, text = { Text("This event") })
            }
            when (tab) {
                0 -> LazyColumn(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (loading && members.isEmpty()) item { Text("Loading…") }
                    items(members, key = { it.id }) { m ->
                        ListItem(
                            headlineContent = { Text(m.name) },
                            supportingContent = {
                                Text(
                                    buildString {
                                        append("Member #${m.id}")
                                        m.userId?.let { append(" · linked user $it") }
                                    },
                                )
                            },
                        )
                    }
                    if (!loading && members.isEmpty()) {
                        item { Text("No members. Tap + to add.") }
                    }
                }
                1 -> LazyColumn(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(expenses, key = { it.id }) { ex ->
                        Column(Modifier.fillMaxWidth()) {
                            Text(
                                "${ex.title} — ${formatInr(ex.amountTotal)} (${ex.expenseDate})",
                                style = MaterialTheme.typography.titleSmall,
                            )
                            Text(ex.category, style = MaterialTheme.typography.bodySmall)
                            ex.splits.forEach { s ->
                                Text("  · ${s.memberName}: ${formatInr(s.amount)}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                    if (!loading && expenses.isEmpty()) {
                        item { Text("No expenses yet.") }
                    }
                }
                2 -> LazyColumn(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    item {
                        val p = orgPoolAvailable
                        Text(
                            if (p != null) {
                                "Unspent organization pool: ${formatInr(BigDecimal.valueOf(p))}"
                            } else {
                                "Organization pool: —"
                            },
                            style = MaterialTheme.typography.titleMedium,
                        )
                    }
                    item {
                        Text(
                            "The pool is shared by every event in this organization. Add or edit entries from the organization screen (web).",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                3 -> LazyColumn(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(balances, key = { it.memberId }) { b ->
                        ListItem(
                            headlineContent = { Text(b.name) },
                            supportingContent = {
                                Text("Share of expenses on this event: ${formatInr(b.expended)}")
                            },
                        )
                    }
                    if (!loading && balances.isEmpty()) {
                        item { Text("No rows (add members first).") }
                    }
                }
            }
        }
    }

    if (showMember) {
        AlertDialog(
            onDismissRequest = { showMember = false },
            title = { Text("Add member") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        newMemberName,
                        { newMemberName = it },
                        label = { Text("Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        newMemberMobile,
                        { newMemberMobile = it },
                        label = { Text("Mobile (optional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val n = newMemberName.trim()
                        if (n.isEmpty()) return@TextButton
                        scope.launch {
                            try {
                                val mob = newMemberMobile.trim().ifBlank { null }
                                app.api.addMember(eventId, MemberCreateRequest(name = n, mobile = mob))
                                newMemberName = ""
                                newMemberMobile = ""
                                showMember = false
                                reloadMembers()
                                reloadBalances()
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text("Add") }
            },
            dismissButton = {
                TextButton(onClick = { showMember = false }) { Text("Cancel") }
            },
        )
    }

    if (showExpense) {
        AlertDialog(
            onDismissRequest = { showExpense = false },
            title = { Text("New expense") },
            text = {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.height(400.dp),
                ) {
                    item {
                        OutlinedTextField(
                            expTitle,
                            { expTitle = it },
                            label = { Text("Title") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    item {
                        OutlinedTextField(
                            expCategory,
                            { expCategory = it },
                            label = { Text("Category") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    item {
                        OutlinedTextField(
                            expTotal,
                            { expTotal = it },
                            label = { Text("Total amount") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    item {
                        OutlinedTextField(
                            expDate,
                            { expDate = it },
                            label = { Text("Date (YYYY-MM-DD)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(expEqualSplit, { expEqualSplit = it })
                            Text("Equal split among selected")
                        }
                    }
                    items(members, key = { it.id }) { m ->
                        if (expEqualSplit) {
                            Row(
                                Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Checkbox(
                                    checked = expInclude[m.id] == true,
                                    onCheckedChange = { expInclude[m.id] = it },
                                )
                                Text(m.name, Modifier.clickable { expInclude[m.id] = !(expInclude[m.id] == true) })
                            }
                        } else {
                            OutlinedTextField(
                                value = expCustomAmounts[m.id].orEmpty(),
                                onValueChange = { expCustomAmounts[m.id] = it },
                                label = { Text("${m.name} amount") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val total = try {
                            BigDecimal(expTotal.trim()).setScale(2, RoundingMode.HALF_UP)
                        } catch (_: Exception) {
                            scope.launch { snackbar.showSnackbar("Invalid total") }
                            return@TextButton
                        }
                        if (total <= BigDecimal.ZERO) {
                            scope.launch { snackbar.showSnackbar("Total must be positive") }
                            return@TextButton
                        }
                        val splits: List<ExpenseSplitInputDto> = if (expEqualSplit) {
                            val ids = members.filter { expInclude[it.id] == true }.map { it.id }
                            if (ids.isEmpty()) {
                                scope.launch { snackbar.showSnackbar("Select at least one member") }
                                return@TextButton
                            }
                            equalSplitRows(total, ids)
                        } else {
                            val rows = mutableListOf<ExpenseSplitInputDto>()
                            for (m in members) {
                                val raw = expCustomAmounts[m.id]?.trim().orEmpty()
                                if (raw.isEmpty()) continue
                                val a = try {
                                    BigDecimal(raw).setScale(2, RoundingMode.HALF_UP)
                                } catch (_: Exception) {
                                    scope.launch { snackbar.showSnackbar("Invalid amount for ${m.name}") }
                                    return@TextButton
                                }
                                if (a > BigDecimal.ZERO) rows.add(ExpenseSplitInputDto(memberId = m.id, amount = a))
                            }
                            if (rows.isEmpty()) {
                                scope.launch { snackbar.showSnackbar("Enter at least one positive amount") }
                                return@TextButton
                            }
                            rows
                        }
                        scope.launch {
                            try {
                                app.api.createExpense(
                                    eventId,
                                    ExpenseCreateRequest(
                                        title = expTitle.trim(),
                                        category = expCategory.trim().ifBlank { "General" },
                                        amountTotal = total,
                                        expenseDate = expDate.trim(),
                                        splits = splits,
                                    ),
                                )
                                expTitle = ""
                                expTotal = ""
                                showExpense = false
                                reloadAll()
                            } catch (e: Exception) {
                                snackbar.showSnackbar(e.rootMessage())
                            }
                        }
                    },
                ) { Text("Save") }
            },
            dismissButton = {
                TextButton(onClick = { showExpense = false }) { Text("Cancel") }
            },
        )
    }
}
