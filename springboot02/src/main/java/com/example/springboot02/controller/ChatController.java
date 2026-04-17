package com.example.springboot02.controller;

import com.example.springboot02.entity.ChatMessage;
import com.example.springboot02.entity.ChatSession;
import com.example.springboot02.entity.Result;
import com.example.springboot02.service.ChatService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@CrossOrigin()
@RestController
public class ChatController {

    @Autowired
    private ChatService chatService;

    @GetMapping("/sessions")
    public Result<List<ChatSession>> getSessionsByUserId(@RequestParam Long userId) {
        if (userId == null) {
            return Result.error("\u7528\u6237ID\u4e0d\u80fd\u4e3a\u7a7a");
        }

        List<ChatSession> list = chatService.getSessionsByUserId(userId);
        return Result.success(list);
    }

    @GetMapping("/allSessions")
    public Result<List<ChatSession>> getAllSessions() {
        List<ChatSession> list = chatService.getAllSessions();
        return Result.success(list);
    }

    @GetMapping("/messages")
    public Result<List<ChatMessage>> getMessages(@RequestParam Long sessionId) {
        if (sessionId == null) {
            return Result.error("\u4f1a\u8bddID\u4e0d\u80fd\u4e3a\u7a7a");
        }

        List<ChatMessage> list = chatService.getMessagesBySessionId(sessionId);
        return Result.success(list);
    }

    @PostMapping("/session")
    public Result<ChatSession> createSession(@RequestParam Long userId, @RequestParam String title) {
        ChatSession session = chatService.createSession(userId, title);
        return Result.success(session);
    }

    @PostMapping("/send")
    public Result<Void> send(@RequestParam Long sessionId, @RequestParam String content) {
        try {
            chatService.sendAndReply(sessionId, content);
            return Result.success();
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @PostMapping("/delete")
    public Result<Void> delete(@RequestParam Long sessionId) {
        try {
            boolean flag = chatService.deleteSession(sessionId);
            return flag ? Result.success() : Result.error("\u5220\u9664\u5931\u8d25");
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }
}
