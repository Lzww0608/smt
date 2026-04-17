package com.example.springboot02.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

@Service
public class SmtTransformClient {

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final String transformUrl;

    public SmtTransformClient(
            RestTemplateBuilder restTemplateBuilder,
            ObjectMapper objectMapper,
            @Value("${smt.backend.base-url:http://127.0.0.1:8000}") String baseUrl,
            @Value("${smt.backend.transform-path:/api/v1/smt/transform}") String transformPath,
            @Value("${smt.backend.connect-timeout-seconds:10}") long connectTimeoutSeconds,
            @Value("${smt.backend.read-timeout-seconds:120}") long readTimeoutSeconds
    ) {
        this.objectMapper = objectMapper;
        this.restTemplate = restTemplateBuilder
                .setConnectTimeout(Duration.ofSeconds(connectTimeoutSeconds))
                .setReadTimeout(Duration.ofSeconds(readTimeoutSeconds))
                .build();
        this.transformUrl = normalizeBaseUrl(baseUrl) + normalizePath(transformPath);
    }

    public TransformResult generateFromText(String content) {
        return transform(content, "natural_language");
    }

    public TransformResult optimizeSmt(String content) {
        return transform(content, "smt_code");
    }

    private TransformResult transform(String content, String contentType) {
        String normalizedContent = normalizeContent(content);
        if (normalizedContent == null) {
            throw new RuntimeException("Request content cannot be empty.");
        }

        Map<String, Object> payload = new HashMap<>();
        payload.put("content", normalizedContent);
        payload.put("content_type", contentType);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> responseBody = restTemplate.postForObject(
                    transformUrl,
                    new HttpEntity<>(payload, headers),
                    Map.class
            );

            if (responseBody == null) {
                throw new RuntimeException("Python SMT service returned an empty response.");
            }

            boolean success = Boolean.TRUE.equals(responseBody.get("success"));
            String result = asText(responseBody.get("result"));
            String message = asText(responseBody.get("message"));

            if (!success) {
                throw new RuntimeException(message != null ? message : "Python SMT service reported failure.");
            }
            if (result == null) {
                throw new RuntimeException("Python SMT service did not return a result.");
            }

            return new TransformResult(result, message);
        } catch (RestClientResponseException ex) {
            throw new RuntimeException(buildRemoteErrorMessage(ex), ex);
        } catch (RestClientException ex) {
            throw new RuntimeException("Failed to connect to the Python SMT service: " + ex.getMessage(), ex);
        }
    }

    private String buildRemoteErrorMessage(RestClientResponseException ex) {
        String responseText = ex.getResponseBodyAsString();
        if (responseText == null || responseText.isBlank()) {
            return "Python SMT service call failed, HTTP " + ex.getRawStatusCode();
        }

        try {
            Map<String, Object> response = objectMapper.readValue(
                    responseText,
                    new TypeReference<Map<String, Object>>() {
                    }
            );
            String message = asText(response.get("message"));
            if (message != null) {
                return "Python SMT service call failed: " + message;
            }
        } catch (Exception ignored) {
            // Fall back to the raw response body below.
        }

        return "Python SMT service call failed: " + responseText;
    }

    private String normalizeBaseUrl(String baseUrl) {
        String normalized = baseUrl == null ? "" : baseUrl.trim();
        if (normalized.endsWith("/")) {
            return normalized.substring(0, normalized.length() - 1);
        }
        return normalized;
    }

    private String normalizePath(String path) {
        String normalized = path == null ? "" : path.trim();
        if (normalized.isEmpty()) {
            return "/api/v1/smt/transform";
        }
        return normalized.startsWith("/") ? normalized : "/" + normalized;
    }

    private String normalizeContent(String content) {
        if (content == null) {
            return null;
        }
        String normalized = content.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private String asText(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof String text) {
            String normalized = text.trim();
            return normalized.isEmpty() ? null : normalized;
        }
        return String.valueOf(value);
    }

    public static class TransformResult {
        private final String result;
        private final String message;

        public TransformResult(String result, String message) {
            this.result = result;
            this.message = message;
        }

        public String getResult() {
            return result;
        }

        public String getMessage() {
            return message;
        }
    }
}
