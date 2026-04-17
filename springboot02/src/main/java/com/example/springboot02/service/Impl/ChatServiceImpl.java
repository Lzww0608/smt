package com.example.springboot02.service.Impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.springboot02.entity.ChatMessage;
import com.example.springboot02.entity.ChatSession;
import com.example.springboot02.mapper.ChatMessageMapper;
import com.example.springboot02.mapper.ChatSessionMapper;
import com.example.springboot02.service.ChatService;
import com.example.springboot02.service.SmtTransformClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class ChatServiceImpl extends ServiceImpl<ChatSessionMapper, ChatSession> implements ChatService {

    private static final String DEFAULT_SESSION_TITLE = "\u672a\u547d\u540d\u4f1a\u8bdd";
    private static final int LAST_MESSAGE_MAX_LENGTH = 500;

    @Autowired
    private ChatMessageMapper chatMessageMapper;

    @Autowired
    private ChatSessionMapper chatSessionMapper;

    @Autowired
    private SmtTransformClient smtTransformClient;

    @Override
    public List<ChatSession> getSessionsByUserId(Long userId) {
        LambdaQueryWrapper<ChatSession> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ChatSession::getUserId, userId)
                .eq(ChatSession::getDeleted, 0)
                .orderByDesc(ChatSession::getUpdateTime);

        return chatSessionMapper.selectList(queryWrapper);
    }

    @Override
    public List<ChatSession> getAllSessions() {
        LambdaQueryWrapper<ChatSession> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ChatSession::getDeleted, 0)
                .orderByDesc(ChatSession::getUpdateTime);

        return chatSessionMapper.selectList(queryWrapper);
    }

    @Override
    public List<ChatMessage> getMessagesBySessionId(Long sessionId) {
        LambdaQueryWrapper<ChatMessage> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(ChatMessage::getSessionId, sessionId)
                .orderByAsc(ChatMessage::getCreateTime);

        return chatMessageMapper.selectList(queryWrapper);
    }

    @Override
    public boolean deleteSession(Long sessionId) {
        if (sessionId == null) {
            throw new RuntimeException("\u4f1a\u8bddID\u4e0d\u80fd\u4e3a\u7a7a");
        }

        ChatSession session = chatSessionMapper.selectById(sessionId);
        if (session == null) {
            throw new RuntimeException("\u4f1a\u8bdd\u4e0d\u5b58\u5728");
        }

        session.setDeleted(1);
        session.setUpdateTime(LocalDateTime.now());
        return chatSessionMapper.updateById(session) > 0;
    }

    @Override
    public ChatSession createSession(Long userId, String title) {
        ChatSession session = new ChatSession();
        session.setUserId(userId);
        session.setTitle(normalizeSessionTitle(title));
        session.setCreateTime(LocalDateTime.now());
        session.setUpdateTime(LocalDateTime.now());
        session.setDeleted(0);

        chatSessionMapper.insert(session);
        return session;
    }

    @Override
    public boolean saveMessage(Long sessionId, String senderType, String content, String messageType) {
        ChatMessage message = new ChatMessage();
        message.setSessionId(sessionId);
        message.setSenderType(senderType);
        message.setContent(content);
        message.setMessageType(messageType);
        message.setCreateTime(LocalDateTime.now());

        int result = chatMessageMapper.insert(message);
        if (result <= 0) {
            return false;
        }

        ChatSession existingSession = chatSessionMapper.selectById(sessionId);
        if (existingSession == null) {
            return false;
        }

        ChatSession session = new ChatSession();
        session.setId(sessionId);
        session.setLastMessage(buildLastMessage(content));
        session.setUpdateTime(LocalDateTime.now());

        if ("user".equalsIgnoreCase(senderType) && shouldUpdateTitle(existingSession.getTitle())) {
            session.setTitle(buildSessionTitle(content));
        }

        chatSessionMapper.updateById(session);
        return true;
    }

    @Override
    public boolean sendAndReply(Long sessionId, String content) {
        if (sessionId == null) {
            throw new RuntimeException("Session id cannot be empty.");
        }

        ChatSession session = chatSessionMapper.selectById(sessionId);
        if (session == null || Integer.valueOf(1).equals(session.getDeleted())) {
            throw new RuntimeException("Session does not exist or has been deleted.");
        }

        String normalizedContent = content == null ? null : content.trim();
        if (normalizedContent == null || normalizedContent.isEmpty()) {
            throw new RuntimeException("Message content cannot be empty.");
        }

        boolean userSaved = saveMessage(sessionId, "user", normalizedContent, "text");
        if (!userSaved) {
            throw new RuntimeException("Failed to save the user message.");
        }

        SmtTransformClient.TransformResult transformResult = smtTransformClient.generateFromText(normalizedContent);
        boolean systemSaved = saveMessage(sessionId, "system", transformResult.getResult(), "smt_code");
        if (!systemSaved) {
            throw new RuntimeException("Failed to save the system reply.");
        }

        return true;
    }

    private boolean shouldUpdateTitle(String title) {
        if (title == null) {
            return true;
        }

        String normalized = title.trim();
        return normalized.isEmpty() || DEFAULT_SESSION_TITLE.equals(normalized);
    }

    private String normalizeSessionTitle(String title) {
        if (title == null || title.trim().isEmpty()) {
            return DEFAULT_SESSION_TITLE;
        }
        return title.trim();
    }

    private String buildSessionTitle(String content) {
        if (content == null) {
            return DEFAULT_SESSION_TITLE;
        }

        String normalized = content.replaceAll("\\s+", " ").trim();
        if (normalized.isEmpty()) {
            return DEFAULT_SESSION_TITLE;
        }

        return normalized.length() > 22 ? normalized.substring(0, 22) : normalized;
    }

    private String buildLastMessage(String content) {
        if (content == null) {
            return "";
        }

        String normalized = content.replace("\r", " ").replace("\n", " ").trim();
        if (normalized.isEmpty()) {
            return "";
        }

        if (normalized.length() <= LAST_MESSAGE_MAX_LENGTH) {
            return normalized;
        }

        return normalized.substring(0, LAST_MESSAGE_MAX_LENGTH - 3) + "...";
    }
}
