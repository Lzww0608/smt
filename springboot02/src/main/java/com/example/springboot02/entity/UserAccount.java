package com.example.springboot02.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("users")
public class UserAccount {
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;
    private String email;
    private String password;
    @TableField("create_time")
    private LocalDateTime createTime;
    @TableField("user_type")
    private Integer userType;
}
