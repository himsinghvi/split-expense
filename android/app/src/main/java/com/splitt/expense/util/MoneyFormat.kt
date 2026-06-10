package com.splitt.expense.util

import java.math.BigDecimal
import java.math.RoundingMode

fun formatInr(amount: BigDecimal): String =
    "₹" + amount.setScale(2, RoundingMode.HALF_UP).toPlainString()

fun formatInr(amount: Double): String =
    "₹" + BigDecimal.valueOf(amount).setScale(2, RoundingMode.HALF_UP).toPlainString()
