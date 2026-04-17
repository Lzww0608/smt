package com.example.springboot02.service;

import com.example.springboot02.entity.UserAccount;

import java.util.List;

public interface LoginService {

    UserAccount login(String email, String password);

    UserAccount register(String email, String password);

    UserAccount updatePassword(Integer id, String password);

    boolean deleteUser(Long id);

    List<UserAccount> getAllUsers();
}
