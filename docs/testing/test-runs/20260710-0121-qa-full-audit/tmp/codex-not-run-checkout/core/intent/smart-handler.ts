#!/usr/bin/env bun
/**
 * Solar Smart Handler - 智能意图理解 + 自主执行
 *
 * 处理模糊输入：文字、链接、图片、语音、文件
 * 自动推断用户意图并执行
 */

import { $ } from 'bun';
import Database from 'bun:sqlite';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;
const SESSIONS_DIR = `${process.env.HOME}/.solar/sessions`;

// 输入类型
type InputType = 'text' | 'url' | 'image' | 'audio' | 'file' | 'unknown';

// 意图类型
type IntentType =
  | 'analyze'      // 分析内容
  | 'summarize'    // 总结
  | 'translate'    // 翻译
  | 'search'       // 搜索
  | 'remind'       // 提醒
  | 'execute'      // 执行任务
  | 'question'     // 回答问题
  | 'learn'        // 学习/研究
  | 'unknown';     // 未知

// 网站登录状态
interface SiteSession {
  site: string;
  domain: string;
  loggedIn: boolean;
  lastCheck: string;
  cookies?: string;
}

// 处理结果
interface HandleResult {
  success: boolean;
  inputType: InputType;
  intent: IntentType;
  needsLogin?: { site: string; url: string };
  content?: string;
  action?: string;
  response?: string;
  error?: string;
}

/**
 * 智能处理器
 */
export class SmartHandler {
  private db: Database;

  constructor() {
    this.db = new Database(DB_PATH);
    this.ensureSessionsDir();
  }

  private async ensureSessionsDir() {
    await $`mkdir -p ${SESSIONS_DIR}`.quiet();
  }

  /**
   * 主入口：处理任意输入
   */
  async handle(input: string): Promise<HandleResult> {
    console.log(`\n🧠 [SmartHandler] 收到输入: ${input.slice(0, 100)}...`);

    // Step 1: 识别输入类型
    const inputType = this.detectInputType(input);
    console.log(`   📝 输入类型: ${inputType}`);

    // Step 2: 获取内容
    const { content, needsLogin } = await this.fetchContent(input, inputType);

    if (needsLogin) {
      console.log(`   🔐 需要登录: ${needsLogin.site}`);
      return {
        success: false,
        inputType,
        intent: 'unknown',
        needsLogin,
        response: `需要登录 ${needsLogin.site}，请回来帮我扫码登录，之后就不用再登录了。`
      };
    }

    // Step 3: 推断意图
    const intent = this.inferIntent(input, content || input);
    console.log(`   🎯 推断意图: ${intent}`);

    // Step 4: 决定行动
    const action = this.decideAction(intent, inputType);
    console.log(`   ⚡ 决定行动: ${action}`);

    // Step 5: 生成响应建议
    const response = this.generateResponse(intent, content || input, action);

    return {
      success: true,
      inputType,
      intent,
      content: content?.slice(0, 500),
      action,
      response
    };
  }

  /**
   * 检测输入类型
   */
  private detectInputType(input: string): InputType {
    const trimmed = input.trim();

    // URL 检测
    if (/^https?:\/\//.test(trimmed)) {
      return 'url';
    }

    // 文件路径检测
    if (/^[\/~].*\.(png|jpg|jpeg|gif|mp3|wav|m4a|pdf|doc|docx|txt|md)$/i.test(trimmed)) {
      const ext = trimmed.split('.').pop()?.toLowerCase();
      if (['png', 'jpg', 'jpeg', 'gif'].includes(ext || '')) return 'image';
      if (['mp3', 'wav', 'm4a'].includes(ext || '')) return 'audio';
      return 'file';
    }

    // 文字
    return 'text';
  }

  /**
   * 获取内容（处理链接、文件等）
   */
  private async fetchContent(input: string, inputType: InputType): Promise<{
    content?: string;
    needsLogin?: { site: string; url: string };
  }> {
    if (inputType === 'url') {
      return this.fetchUrl(input);
    }

    if (inputType === 'image') {
      // 图片需要视觉理解，返回提示
      return { content: `[图片文件: ${input}] 需要视觉分析` };
    }

    if (inputType === 'audio') {
      // 语音需要转录
      return { content: `[语音文件: ${input}] 需要语音转录` };
    }

    if (inputType === 'file') {
      try {
        const content = await Bun.file(input.replace('~', process.env.HOME || '')).text();
        return { content: content.slice(0, 5000) };
      } catch {
        return { content: `[文件读取失败: ${input}]` };
      }
    }

    return { content: input };
  }

  /**
   * 获取 URL 内容
   */
  private async fetchUrl(url: string): Promise<{
    content?: string;
    needsLogin?: { site: string; url: string };
  }> {
    const domain = new URL(url).hostname;
    const site = this.getSiteName(domain);

    // 检查是否需要登录的网站
    const needsLoginSites = ['zhihu.com', 'weibo.com', 'xiaohongshu.com', 'douyin.com'];
    const needsAuth = needsLoginSites.some(s => domain.includes(s));

    if (needsAuth) {
      // 检查是否已登录
      const session = await this.checkSession(site);
      if (!session.loggedIn) {
        return {
          needsLogin: { site, url }
        };
      }
    }

    // 尝试获取内容（这里简化处理，实际会用 Playwright）
    try {
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
      });

      if (response.status === 403 || response.status === 401) {
        return {
          needsLogin: { site, url }
        };
      }

      const html = await response.text();
      // 简单提取文本（实际会更智能）
      const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 3000);
      return { content: text };
    } catch (e) {
      return { content: `[URL 获取失败: ${url}]` };
    }
  }

  /**
   * 从域名获取网站名
   */
  private getSiteName(domain: string): string {
    const siteMap: Record<string, string> = {
      'zhihu.com': '知乎',
      'weibo.com': '微博',
      'xiaohongshu.com': '小红书',
      'douyin.com': '抖音',
      'github.com': 'GitHub',
      'twitter.com': 'Twitter',
      'x.com': 'Twitter',
    };

    for (const [d, name] of Object.entries(siteMap)) {
      if (domain.includes(d)) return name;
    }
    return domain;
  }

  /**
   * 检查网站登录状态
   */
  private async checkSession(site: string): Promise<SiteSession> {
    const sessionFile = `${SESSIONS_DIR}/${site.toLowerCase().replace(/\s/g, '_')}.json`;

    try {
      const file = Bun.file(sessionFile);
      if (await file.exists()) {
        const session = await file.json() as SiteSession;
        // 检查是否过期（7天）
        const lastCheck = new Date(session.lastCheck);
        const now = new Date();
        const daysDiff = (now.getTime() - lastCheck.getTime()) / (1000 * 60 * 60 * 24);

        if (daysDiff < 7 && session.loggedIn) {
          return session;
        }
      }
    } catch {}

    return {
      site,
      domain: '',
      loggedIn: false,
      lastCheck: new Date().toISOString()
    };
  }

  /**
   * 保存登录状态
   */
  async saveSession(site: string, loggedIn: boolean, cookies?: string): Promise<void> {
    const sessionFile = `${SESSIONS_DIR}/${site.toLowerCase().replace(/\s/g, '_')}.json`;
    const session: SiteSession = {
      site,
      domain: '',
      loggedIn,
      lastCheck: new Date().toISOString(),
      cookies
    };
    await Bun.write(sessionFile, JSON.stringify(session, null, 2));
    console.log(`   💾 已保存 ${site} 登录状态`);
  }

  /**
   * 推断用户意图
   */
  private inferIntent(originalInput: string, content: string): IntentType {
    const input = (originalInput + ' ' + content).toLowerCase();

    // 关键词匹配
    const intentPatterns: Array<{ patterns: RegExp[]; intent: IntentType }> = [
      {
        patterns: [/分析|看看|研究|了解|什么意思/],
        intent: 'analyze'
      },
      {
        patterns: [/总结|概括|摘要|简述/],
        intent: 'summarize'
      },
      {
        patterns: [/翻译|translate/],
        intent: 'translate'
      },
      {
        patterns: [/搜索|搜一下|查一下|找一下/],
        intent: 'search'
      },
      {
        patterns: [/提醒|remind|记得|别忘/],
        intent: 'remind'
      },
      {
        patterns: [/执行|运行|做|干|帮我/],
        intent: 'execute'
      },
      {
        patterns: [/\?|？|吗|呢|什么|怎么|为什么|如何/],
        intent: 'question'
      },
      {
        patterns: [/学习|研究|深入|详细/],
        intent: 'learn'
      }
    ];

    for (const { patterns, intent } of intentPatterns) {
      if (patterns.some(p => p.test(input))) {
        return intent;
      }
    }

    // 默认：如果是链接，推断为分析
    if (this.detectInputType(originalInput) === 'url') {
      return 'analyze';
    }

    return 'unknown';
  }

  /**
   * 决定行动
   */
  private decideAction(intent: IntentType, inputType: InputType): string {
    const actionMap: Record<IntentType, string> = {
      'analyze': '分析内容并给出见解',
      'summarize': '总结核心要点',
      'translate': '翻译内容',
      'search': '搜索相关信息',
      'remind': '设置提醒 (solar_set_reminder)',
      'execute': '执行具体任务',
      'question': '回答问题',
      'learn': '深入研究并整理知识',
      'unknown': '理解用户需求后再行动'
    };

    let action = actionMap[intent];

    // 根据输入类型调整
    if (inputType === 'image') {
      action = `视觉分析图片 → ${action}`;
    } else if (inputType === 'audio') {
      action = `转录语音 → ${action}`;
    } else if (inputType === 'url') {
      action = `获取网页内容 → ${action}`;
    }

    return action;
  }

  /**
   * 生成响应
   */
  private generateResponse(intent: IntentType, content: string, action: string): string {
    const templates: Record<IntentType, string> = {
      'analyze': `我来分析一下这个内容...\n\n行动: ${action}`,
      'summarize': `我来总结一下要点...\n\n行动: ${action}`,
      'translate': `我来翻译一下...\n\n行动: ${action}`,
      'search': `我来搜索一下相关信息...\n\n行动: ${action}`,
      'remind': `好的，我来设置提醒...\n\n行动: ${action}`,
      'execute': `好的，我来执行这个任务...\n\n行动: ${action}`,
      'question': `让我来回答这个问题...\n\n行动: ${action}`,
      'learn': `我来深入研究一下...\n\n行动: ${action}`,
      'unknown': `我理解你的需求，让我想想该怎么做...\n\n行动: ${action}`
    };

    return templates[intent];
  }

  close() {
    this.db.close();
  }
}

// CLI 测试
if (import.meta.main) {
  const handler = new SmartHandler();
  const input = process.argv.slice(2).join(' ') || '帮我分析一下这个';

  handler.handle(input).then(result => {
    console.log('\n' + '='.repeat(60));
    console.log('处理结果:');
    console.log(JSON.stringify(result, null, 2));
    handler.close();
  });
}
