package com.splitt.expense.network

import com.google.gson.annotations.SerializedName
import java.math.BigDecimal

data class UserRegisterRequest(
    val mobile: String,
    val password: String,
    @SerializedName("full_name") val fullName: String,
)

data class RegisterResponse(
    val id: Long,
    val mobile: String,
    @SerializedName("full_name") val fullName: String,
)

data class UserLoginRequest(
    val mobile: String,
    val password: String,
)

data class TokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
)

data class UserMe(
    val id: Long,
    val mobile: String,
    @SerializedName("full_name") val fullName: String,
    @SerializedName("total_contributed") val totalContributed: Double = 0.0,
    @SerializedName("total_expended") val totalExpended: Double = 0.0,
    @SerializedName("total_remaining") val totalRemaining: Double = 0.0,
)

data class OrganizationRead(
    val id: Long,
    val name: String,
)

data class EventRead(
    val id: Long,
    @SerializedName("organization_id") val organizationId: Long,
    val name: String,
)

data class MemberRead(
    val id: Long,
    @SerializedName("event_id") val eventId: Long,
    val name: String,
    @SerializedName("user_id") val userId: Long?,
)

data class MemberCreateRequest(
    val name: String,
    val mobile: String? = null,
)

data class ContributionCreateRequest(
    @SerializedName("member_id") val memberId: Long,
    val amount: BigDecimal,
    val note: String? = null,
)

data class ContributionRead(
    val id: Long,
    @SerializedName("member_id") val memberId: Long,
    val amount: BigDecimal,
    val note: String?,
    @SerializedName("created_at") val createdAt: String,
)

data class ExpenseSplitInputDto(
    @SerializedName("member_id") val memberId: Long,
    val amount: BigDecimal? = null,
    val percent: BigDecimal? = null,
)

data class ExpenseCreateRequest(
    val title: String,
    val category: String,
    @SerializedName("amount_total") val amountTotal: BigDecimal,
    @SerializedName("expense_date") val expenseDate: String,
    val splits: List<ExpenseSplitInputDto>,
)

data class ExpenseSplitRead(
    @SerializedName("member_id") val memberId: Long,
    @SerializedName("member_name") val memberName: String,
    val amount: BigDecimal,
)

data class ExpenseRead(
    val id: Long,
    @SerializedName("event_id") val eventId: Long,
    val title: String,
    val category: String,
    @SerializedName("amount_total") val amountTotal: BigDecimal,
    @SerializedName("expense_date") val expenseDate: String,
    val splits: List<ExpenseSplitRead> = emptyList(),
)

data class MemberBalanceRead(
    @SerializedName("member_id") val memberId: Long,
    val name: String,
    val contributed: BigDecimal,
    val expended: BigDecimal,
    val remaining: BigDecimal,
)

data class OrgMemberInviteRequest(val mobile: String)

data class OkResponse(val ok: Boolean = true)
