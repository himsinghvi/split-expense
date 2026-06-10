package com.splitt.expense.network

import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Streaming

interface ApiService {

    @POST("auth/register")
    suspend fun register(@Body body: UserRegisterRequest): RegisterResponse

    @POST("auth/login")
    suspend fun login(@Body body: UserLoginRequest): TokenResponse

    @GET("me")
    suspend fun me(): UserMe

    @GET("organizations")
    suspend fun organizations(): List<OrganizationRead>

    @POST("organizations")
    suspend fun createOrganization(@Body body: Map<String, String>): OrganizationRead

    @GET("organizations/{orgId}")
    suspend fun getOrganization(@Path("orgId") orgId: Long): OrganizationRead

    @POST("organizations/{orgId}/members")
    suspend fun inviteOrgMember(
        @Path("orgId") orgId: Long,
        @Body body: OrgMemberInviteRequest,
    ): OkResponse

    @GET("organizations/{orgId}/events")
    suspend fun listEvents(@Path("orgId") orgId: Long): List<EventRead>

    @POST("organizations/{orgId}/events")
    suspend fun createEvent(
        @Path("orgId") orgId: Long,
        @Body body: Map<String, String>,
    ): EventRead

    @GET("events/{eventId}")
    suspend fun getEvent(@Path("eventId") eventId: Long): EventRead

    @GET("events/{eventId}/members")
    suspend fun members(@Path("eventId") eventId: Long): List<MemberRead>

    @POST("events/{eventId}/members")
    suspend fun addMember(
        @Path("eventId") eventId: Long,
        @Body body: MemberCreateRequest,
    ): MemberRead

    @GET("events/{eventId}/contributions")
    suspend fun contributions(@Path("eventId") eventId: Long): List<ContributionRead>

    @POST("events/{eventId}/contributions")
    suspend fun addContribution(
        @Path("eventId") eventId: Long,
        @Body body: ContributionCreateRequest,
    ): ContributionRead

    @GET("events/{eventId}/expenses")
    suspend fun expenses(@Path("eventId") eventId: Long): List<ExpenseRead>

    @POST("events/{eventId}/expenses")
    suspend fun createExpense(
        @Path("eventId") eventId: Long,
        @Body body: ExpenseCreateRequest,
    ): ExpenseRead

    @GET("events/{eventId}/balances")
    suspend fun balances(@Path("eventId") eventId: Long): List<MemberBalanceRead>

    @Streaming
    @GET("events/{eventId}/export.xlsx")
    suspend fun exportXlsx(@Path("eventId") eventId: Long): ResponseBody
}
