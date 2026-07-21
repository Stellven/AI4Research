//! Chinese tokenizer using jieba-rs
//!
//! Provides high-quality Chinese word segmentation for full-text search.

use jieba_rs::Jieba;
use std::sync::Arc;
use tantivy::tokenizer::{Token, TokenStream, Tokenizer};

/// Jieba-based tokenizer for Chinese text
#[derive(Clone)]
pub struct JiebaTokenizer {
    jieba: Arc<Jieba>,
}

impl Default for JiebaTokenizer {
    fn default() -> Self {
        Self::new()
    }
}

impl JiebaTokenizer {
    pub fn new() -> Self {
        Self {
            jieba: Arc::new(Jieba::new()),
        }
    }

    /// Create with custom dictionary
    pub fn with_dict(dict_path: &str) -> anyhow::Result<Self> {
        let mut jieba = Jieba::new();
        // Load custom dictionary if exists
        if std::path::Path::new(dict_path).exists() {
            let content = std::fs::read_to_string(dict_path)?;
            for line in content.lines() {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if let Some(word) = parts.first() {
                    let freq = parts.get(1).and_then(|s| s.parse().ok());
                    let tag = parts.get(2).map(|s| s.to_string());
                    jieba.add_word(word, freq, tag.as_deref());
                }
            }
        }
        Ok(Self {
            jieba: Arc::new(jieba),
        })
    }
}

impl Tokenizer for JiebaTokenizer {
    type TokenStream<'a> = JiebaTokenStream;

    fn token_stream<'a>(&'a mut self, text: &'a str) -> Self::TokenStream<'a> {
        let tokens: Vec<(String, usize, usize)> = self
            .jieba
            .tokenize(text, jieba_rs::TokenizeMode::Search, true)
            .into_iter()
            .map(|t| (t.word.to_string(), t.start, t.end))
            .collect();

        JiebaTokenStream {
            tokens,
            index: 0,
            token: Token::default(),
        }
    }
}

pub struct JiebaTokenStream {
    tokens: Vec<(String, usize, usize)>,
    index: usize,
    token: Token,
}

impl TokenStream for JiebaTokenStream {
    fn advance(&mut self) -> bool {
        if self.index < self.tokens.len() {
            let (text, start, end) = &self.tokens[self.index];
            self.token = Token {
                offset_from: *start,
                offset_to: *end,
                position: self.index,
                text: text.clone(),
                position_length: 1,
            };
            self.index += 1;
            true
        } else {
            false
        }
    }

    fn token(&self) -> &Token {
        &self.token
    }

    fn token_mut(&mut self) -> &mut Token {
        &mut self.token
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chinese_tokenization() {
        let mut tokenizer = JiebaTokenizer::new();
        let mut stream = tokenizer.token_stream("我要搜索GPU性能优化");

        let mut tokens = vec![];
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        // Should segment into meaningful words
        assert!(tokens.contains(&"GPU".to_string()) || tokens.contains(&"性能".to_string()));
    }

    #[test]
    fn test_english_passthrough() {
        let mut tokenizer = JiebaTokenizer::new();
        let mut stream = tokenizer.token_stream("Hello World Tantivy");

        let mut tokens = vec![];
        while stream.advance() {
            tokens.push(stream.token().text.clone());
        }

        assert!(!tokens.is_empty());
    }
}
