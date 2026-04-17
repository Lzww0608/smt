package com.example.springboot02.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("chat_message")
public class ChatMessage {
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;
    @TableField("session_id")
    private Long sessionId;
    @TableField("sender_type")
    private String senderType;
    private String content;
    @TableField("message_type")
    private String messageType;
    @TableField("create_time")
    private LocalDateTime createTime;
}
