package com.example.springboot02.controller;

import com.example.springboot02.entity.Result;
import com.example.springboot02.entity.UserAccount;
import com.example.springboot02.service.LoginService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@CrossOrigin()
@RestController
public class LoginController {

    @Autowired
    private LoginService loginService;

    @PostMapping("/login")
    public Result<UserAccount> login(@RequestParam String email, @RequestParam String password) {
        UserAccount user = loginService.login(email, password);
        if (user != null) {
            user.setPassword(null);
            return Result.success(user);
        }
        return Result.error("\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef");
    }

    @PostMapping("/register")
    public Result<UserAccount> register(@RequestParam String email, @RequestParam String password) {
        try {
            UserAccount user = loginService.register(email, password);
            user.setPassword(null);
            return Result.success(user);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @PostMapping("/updatePassword")
    public Result<UserAccount> updatePassword(@RequestParam Integer id, @RequestParam String password) {
        try {
            UserAccount user = loginService.updatePassword(id, password);
            return Result.success(user);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @PostMapping("/deleteUser")
    public Result<Void> deleteUser(@RequestParam Long id) {
        try {
            boolean success = loginService.deleteUser(id);
            return success ? Result.success() : Result.error("\u5220\u9664\u7528\u6237\u5931\u8d25");
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @GetMapping("/users")
    public Result<List<UserAccount>> getAllUsers() {
        try {
            List<UserAccount> users = loginService.getAllUsers();
            return Result.success(users);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }
}
