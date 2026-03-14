package com.aura.aura_ui.data.database

/**
 * Database class for the AURA application.
 * For now, this is just a placeholder class.
 */
class AuraDatabase {
    fun audioDao(): AudioDao {
        return object : AudioDao {}
    }
}
