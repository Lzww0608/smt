package com.example.springboot02.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("optimize_record")
public class OptimizeRecord {

    @TableId(value = "opt_id", type = IdType.AUTO)
    private Long optId;

    @TableField("message_id")
    private Long messageId;

    @TableField("original_code")
    private String originalCode;

    @TableField("optimized_code")
    private String optimizedCode;

    @TableField("create_time")
    private LocalDateTime createTime;
}
