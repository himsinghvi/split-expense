package com.splitt.expense.util

import com.splitt.expense.network.ExpenseSplitInputDto
import java.math.BigDecimal
import java.math.RoundingMode

fun equalSplitRows(total: BigDecimal, memberIds: List<Long>): List<ExpenseSplitInputDto> {
    if (memberIds.isEmpty()) return emptyList()
    val totalCents = total.setScale(2, RoundingMode.HALF_UP).movePointRight(2).toLong()
    val n = memberIds.size
    val each = totalCents / n
    val rem = (totalCents % n).toInt()
    return memberIds.mapIndexed { idx, id ->
        val cents = each + if (idx < rem) 1 else 0
        val amt = BigDecimal.valueOf(cents).movePointLeft(2)
        ExpenseSplitInputDto(memberId = id, amount = amt, percent = null)
    }
}
