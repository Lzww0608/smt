package com.example.springboot02.service;

import com.example.springboot02.entity.OptimizeRecord;

import java.util.List;

public interface OptimizeRecordService {
    List<OptimizeRecord> getAllOptimizeRecords();

    List<OptimizeRecord> getOptimizeRecordsByMessageId(Long messageId);

    OptimizeRecord optimizeCode(Long messageId, String originalCode);

    boolean deleteOptimizeRecord(Long optId);
}
