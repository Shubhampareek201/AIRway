package com.airwayservices.airway

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        createAirwayNotificationChannels()
    }

    private fun createAirwayNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
            .build()

        val jobAlerts = NotificationChannel(
            "airway_job_alerts",
            "AIRway Job Requests",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Urgent new service requests that need a worker response"
            enableVibration(true)
            setSound(sound, audioAttributes)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }

        val general = NotificationChannel(
            "airway_general",
            "AIRway Updates",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "Booking, account and payment updates"
            setSound(sound, audioAttributes)
        }

        manager.createNotificationChannels(listOf(jobAlerts, general))
    }
}
