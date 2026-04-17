package com.example.springboot02.controller;

import com.example.springboot02.entity.OptimizeRecord;
import com.example.springboot02.entity.Result;
import com.example.springboot02.service.OptimizeRecordService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@CrossOrigin()
@RestController
public class OptimizeRecordController {

    @Autowired
    private OptimizeRecordService optimizeRecordService;

    @GetMapping("/optimizeRecords")
    public Result<List<OptimizeRecord>> getAllOptimizeRecords() {
        try {
            List<OptimizeRecord> list = optimizeRecordService.getAllOptimizeRecords();
            return Result.success(list);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @GetMapping("/optimizeRecords/byMessage")
    public Result<List<OptimizeRecord>> getOptimizeRecordsByMessageId(@RequestParam Long messageId) {
        try {
            if (messageId == null) {
                return Result.error("\u006d\u0065\u0073\u0073\u0061\u0067\u0065\u0049\u0064\u4e0d\u80fd\u4e3a\u7a7a");
            }
            List<OptimizeRecord> list = optimizeRecordService.getOptimizeRecordsByMessageId(messageId);
            return Result.success(list);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @PostMapping("/optimizeCode")
    public Result<OptimizeRecord> optimizeCode(
            @RequestParam Long messageId,
            @RequestParam(required = false) String originalCode
    ) {
        try {
            OptimizeRecord record = optimizeRecordService.optimizeCode(messageId, originalCode);
            return Result.success(record);
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }

    @PostMapping("/deleteOptimizeRecord")
    public Result<Void> deleteOptimizeRecord(@RequestParam Long optId) {
        try {
            boolean flag = optimizeRecordService.deleteOptimizeRecord(optId);
            return flag ? Result.success() : Result.error("\u5220\u9664\u4f18\u5316\u8bb0\u5f55\u5931\u8d25");
        } catch (RuntimeException e) {
            return Result.error(e.getMessage());
        }
    }
}
