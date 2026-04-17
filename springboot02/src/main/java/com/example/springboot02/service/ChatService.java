package com.example.springboot02.service;

import com.example.springboot02.entity.ChatMessage;
import com.example.springboot02.entity.ChatSession;

import java.util.List;

public interface ChatService {

    List<ChatSession> getSessionsByUserId(Long userId);

    List<ChatSession> getAllSessions();

    List<ChatMessage> getMessagesBySessionId(Long sessionId);

    boolean deleteSession(Long sessionId);

    ChatSession createSession(Long userId, String title);

    boolean saveMessage(Long sessionId, String senderType, String content, String messageType);

    boolean sendAndReply(Long sessionId, String content);
}
