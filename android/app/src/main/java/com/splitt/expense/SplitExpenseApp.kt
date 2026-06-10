package com.splitt.expense

import android.app.Application
import com.splitt.expense.network.ApiService
import com.splitt.expense.network.buildApi

class SplitExpenseApp : Application() {
    lateinit var session: SessionStore
        private set
    lateinit var api: ApiService
        private set

    override fun onCreate() {
        super.onCreate()
        session = SessionStore(this)
        api = buildApi(session)
    }
}
