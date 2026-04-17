package com.example.springboot02.service.Impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.springboot02.entity.ChatMessage;
import com.example.springboot02.entity.OptimizeRecord;
import com.example.springboot02.mapper.ChatMessageMapper;
import com.example.springboot02.mapper.OptimizeRecordMapper;
import com.example.springboot02.service.OptimizeRecordService;
import com.example.springboot02.service.SmtTransformClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class OptimizeRecordServiceImpl extends ServiceImpl<OptimizeRecordMapper, OptimizeRecord> implements OptimizeRecordService {

    @Autowired
    private OptimizeRecordMapper optimizeRecordMapper;

    @Autowired
    private ChatMessageMapper chatMessageMapper;

    @Autowired
    private SmtTransformClient smtTransformClient;

    @Override
    public List<OptimizeRecord> getAllOptimizeRecords() {
        LambdaQueryWrapper<OptimizeRecord> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.orderByDesc(OptimizeRecord::getCreateTime)
                .orderByDesc(OptimizeRecord::getOptId);
        return optimizeRecordMapper.selectList(queryWrapper);
    }

    @Override
    public List<OptimizeRecord> getOptimizeRecordsByMessageId(Long messageId) {
        LambdaQueryWrapper<OptimizeRecord> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(OptimizeRecord::getMessageId, messageId)
                .orderByAsc(OptimizeRecord::getCreateTime)
                .orderByAsc(OptimizeRecord::getOptId);
        return optimizeRecordMapper.selectList(queryWrapper);
    }

    @Override
    public OptimizeRecord optimizeCode(Long messageId, String originalCode) {
        if (messageId == null) {
            throw new RuntimeException("\u006d\u0065\u0073\u0073\u0061\u0067\u0065\u0049\u0064\u4e0d\u80fd\u4e3a\u7a7a");
        }

        ChatMessage message = chatMessageMapper.selectById(messageId);
        if (message == null) {
            throw new RuntimeException("\u672a\u627e\u5230\u5bf9\u5e94\u7684\u6d88\u606f\u8bb0\u5f55");
        }
        if (!"system".equalsIgnoreCase(message.getSenderType())) {
            throw new RuntimeException("\u53ea\u80fd\u5bf9\u7cfb\u7edf\u56de\u590d\u8fdb\u884c\u4ee3\u7801\u4f18\u5316");
        }

        String resolvedOriginalCode = resolveOriginalCode(messageId, message, originalCode);
        String optimizedCode = performOptimize(resolvedOriginalCode);

        OptimizeRecord record = new OptimizeRecord();
        record.setMessageId(messageId);
        record.setOriginalCode(resolvedOriginalCode);
        record.setOptimizedCode(optimizedCode);
        record.setCreateTime(LocalDateTime.now());

        int rows = optimizeRecordMapper.insert(record);
        if (rows <= 0) {
            throw new RuntimeException("\u4f18\u5316\u4ee3\u7801\u4fdd\u5b58\u5931\u8d25");
        }

        return record;
    }

    @Override
    public boolean deleteOptimizeRecord(Long optId) {
        if (optId == null) {
            throw new RuntimeException("\u4f18\u5316\u8bb0\u5f55ID\u4e0d\u80fd\u4e3a\u7a7a");
        }

        OptimizeRecord record = optimizeRecordMapper.selectById(optId);
        if (record == null) {
            throw new RuntimeException("\u4f18\u5316\u8bb0\u5f55\u4e0d\u5b58\u5728");
        }

        int rows = optimizeRecordMapper.deleteById(optId);
        if (rows <= 0) {
            throw new RuntimeException("\u5220\u9664\u4f18\u5316\u8bb0\u5f55\u5931\u8d25");
        }

        return true;
    }

    private String resolveOriginalCode(Long messageId, ChatMessage message, String requestOriginalCode) {
        String normalizedRequestCode = normalizeCode(requestOriginalCode);
        if (normalizedRequestCode != null) {
            return normalizedRequestCode;
        }

        LambdaQueryWrapper<OptimizeRecord> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(OptimizeRecord::getMessageId, messageId)
                .orderByDesc(OptimizeRecord::getCreateTime)
                .orderByDesc(OptimizeRecord::getOptId)
                .last("limit 1");

        OptimizeRecord latestRecord = optimizeRecordMapper.selectOne(queryWrapper);
        String latestOptimizedCode = latestRecord == null ? null : normalizeCode(latestRecord.getOptimizedCode());
        if (latestOptimizedCode != null) {
            return latestOptimizedCode;
        }

        String content = normalizeCode(message.getContent());
        if (content == null) {
            throw new RuntimeException("\u8be5\u7cfb\u7edf\u6d88\u606f\u4e0d\u5b58\u5728\u53ef\u4f9b\u4f18\u5316\u7684\u4ee3\u7801");
        }
        return content;
    }

    private String normalizeCode(String code) {
        if (code == null) {
            return null;
        }

        String normalized = code.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private String performOptimize(String sourceCode) {
        String normalizedSourceCode = normalizeCode(sourceCode);
        if (normalizedSourceCode == null) {
            throw new RuntimeException("\u539f\u59cb\u4ee3\u7801\u4e0d\u80fd\u4e3a\u7a7a");
        }

        return smtTransformClient.optimizeSmt(normalizedSourceCode).getResult();
    }
}
