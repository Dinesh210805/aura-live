package com.aura.aura_ui

import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class ConversationAdapter(private val messages: List<ConversationMessage>) :
    RecyclerView.Adapter<ConversationAdapter.MessageViewHolder>() {
    class MessageViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val messageText: TextView = view.findViewById(R.id.messageText)
        val messageContainer: LinearLayout = view.findViewById(R.id.messageContainer)
    }

    override fun onCreateViewHolder(
        parent: ViewGroup,
        viewType: Int,
    ): MessageViewHolder {
        val view =
            LayoutInflater.from(parent.context)
                .inflate(R.layout.item_conversation_message, parent, false)
        return MessageViewHolder(view)
    }

    override fun onBindViewHolder(
        holder: MessageViewHolder,
        position: Int,
    ) {
        val message = messages[position]
        holder.messageText.text = message.text

        // Style based on sender
        val layoutParams = holder.messageContainer.layoutParams as LinearLayout.LayoutParams
        if (message.isUser) {
            layoutParams.gravity = Gravity.END
            holder.messageContainer.setBackgroundResource(R.drawable.user_message_background)
        } else {
            layoutParams.gravity = Gravity.START
            holder.messageContainer.setBackgroundResource(R.drawable.aura_message_background)
        }
        holder.messageContainer.layoutParams = layoutParams
    }

    override fun getItemCount() = messages.size
}
