package com.example.springboot02.service.Impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.springboot02.entity.UserAccount;
import com.example.springboot02.mapper.LoginMapper;
import com.example.springboot02.service.LoginService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class LoginServiceImpl extends ServiceImpl<LoginMapper, UserAccount> implements LoginService {

    @Autowired
    private LoginMapper loginMapper;

    @Override
    public UserAccount login(String email, String password) {
        LambdaQueryWrapper<UserAccount> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(UserAccount::getEmail, email)
                .eq(UserAccount::getPassword, password);

        return loginMapper.selectOne(queryWrapper);
    }

    @Override
    public UserAccount register(String email, String password) {
        if (email == null || email.trim().isEmpty()) {
            throw new RuntimeException("\u90ae\u7bb1\u4e0d\u80fd\u4e3a\u7a7a");
        }
        if (password == null || password.trim().isEmpty()) {
            throw new RuntimeException("\u5bc6\u7801\u4e0d\u80fd\u4e3a\u7a7a");
        }

        LambdaQueryWrapper<UserAccount> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(UserAccount::getEmail, email);

        UserAccount existUser = loginMapper.selectOne(queryWrapper);
        if (existUser != null) {
            throw new RuntimeException("\u8be5\u90ae\u7bb1\u5df2\u88ab\u6ce8\u518c");
        }

        UserAccount user = new UserAccount();
        user.setEmail(email);
        user.setPassword(password);
        user.setCreateTime(LocalDateTime.now());

        int rows = loginMapper.insert(user);
        if (rows <= 0) {
            throw new RuntimeException("\u6ce8\u518c\u5931\u8d25");
        }

        return user;
    }

    @Override
    public UserAccount updatePassword(Integer id, String password) {
        if (id == null) {
            throw new RuntimeException("\u7528\u6237id\u4e0d\u80fd\u4e3a\u7a7a");
        }
        if (password == null || password.trim().isEmpty()) {
            throw new RuntimeException("\u65b0\u5bc6\u7801\u4e0d\u80fd\u4e3a\u7a7a");
        }

        UserAccount user = loginMapper.selectById(id);
        if (user == null) {
            throw new RuntimeException("\u7528\u6237\u4e0d\u5b58\u5728");
        }

        user.setPassword(password);

        int rows = loginMapper.updateById(user);
        if (rows <= 0) {
            throw new RuntimeException("\u5bc6\u7801\u4fee\u6539\u5931\u8d25");
        }

        user.setPassword(null);
        return user;
    }

    @Override
    public boolean deleteUser(Long id) {
        if (id == null) {
            throw new RuntimeException("\u7528\u6237id\u4e0d\u80fd\u4e3a\u7a7a");
        }

        UserAccount user = loginMapper.selectById(id);
        if (user == null) {
            throw new RuntimeException("\u7528\u6237\u4e0d\u5b58\u5728");
        }

        try {
            int rows = loginMapper.deleteById(id);
            if (rows <= 0) {
                throw new RuntimeException("\u5220\u9664\u7528\u6237\u5931\u8d25");
            }
            return true;
        } catch (DataIntegrityViolationException e) {
            throw new RuntimeException("\u8be5\u7528\u6237\u5b58\u5728\u5173\u8054\u4f1a\u8bdd\u6216\u804a\u5929\u8bb0\u5f55\uff0c\u65e0\u6cd5\u5220\u9664");
        }
    }

    @Override
    public List<UserAccount> getAllUsers() {
        return loginMapper.selectList(null);
    }
}
