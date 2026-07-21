/**
 * Solar AI OS - Apple Contacts & FaceTime 集成
 *
 * 功能:
 * 1. 读取 Apple 通讯录联系人
 * 2. 模糊搜索联系人
 * 3. 发起 FaceTime 音频/视频通话
 * 4. 发起普通电话 (通过 iPhone)
 */

import { execSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";

// ==================== Types ====================

export interface Contact {
  id: string;
  name: string;
  nickname?: string;
  phones: { label: string; number: string }[];
  emails: { label: string; address: string }[];
  organization?: string;
  note?: string;
}

export interface CallResult {
  success: boolean;
  method: "facetime-video" | "facetime-audio" | "phone";
  target: string;
  contactName?: string;
  error?: string;
}

// ==================== Contacts Manager ====================

export class AppleContactsManager {
  private contacts: Contact[] = [];
  private cachePath: string;
  private cacheMaxAge = 3600000; // 1 hour
  private lastCacheTime = 0;

  constructor() {
    this.cachePath = join(process.env.HOME ?? "~", ".solar", "contacts-cache.json");
    this.ensureCacheDir();
    this.loadCache();
  }

  private ensureCacheDir(): void {
    const dir = join(process.env.HOME ?? "~", ".solar");
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
  }

  private loadCache(): void {
    if (existsSync(this.cachePath)) {
      try {
        const cache = JSON.parse(readFileSync(this.cachePath, "utf-8"));
        if (Date.now() - cache.timestamp < this.cacheMaxAge) {
          this.contacts = cache.contacts;
          this.lastCacheTime = cache.timestamp;
        }
      } catch {
        // Ignore cache errors
      }
    }
  }

  private saveCache(): void {
    try {
      writeFileSync(this.cachePath, JSON.stringify({
        timestamp: Date.now(),
        contacts: this.contacts,
      }, null, 2));
    } catch {
      // Ignore save errors
    }
  }

  /**
   * 从 Apple Contacts 加载联系人
   */
  async loadContacts(forceRefresh = false): Promise<Contact[]> {
    if (!forceRefresh && this.contacts.length > 0 && Date.now() - this.lastCacheTime < this.cacheMaxAge) {
      return this.contacts;
    }

    try {
      // 使用 AppleScript 读取联系人
      const script = `
        set output to ""
        tell application "Contacts"
          repeat with p in people
            set pName to name of p
            set pId to id of p
            set pNickname to ""
            try
              set pNickname to nickname of p
            end try
            set pOrg to ""
            try
              set pOrg to organization of p
            end try

            -- 获取电话号码
            set phoneList to ""
            repeat with ph in phones of p
              set phoneList to phoneList & (label of ph) & ":" & (value of ph) & ";"
            end repeat

            -- 获取邮箱
            set emailList to ""
            repeat with em in emails of p
              set emailList to emailList & (label of em) & ":" & (value of em) & ";"
            end repeat

            set output to output & pId & "|" & pName & "|" & pNickname & "|" & pOrg & "|" & phoneList & "|" & emailList & "\\n"
          end repeat
        end tell
        return output
      `;

      const result = execSync(`osascript -e '${script.replace(/'/g, "'\"'\"'")}'`, {
        encoding: "utf-8",
        maxBuffer: 10 * 1024 * 1024,
      });

      this.contacts = this.parseContactsOutput(result);
      this.lastCacheTime = Date.now();
      this.saveCache();

      return this.contacts;
    } catch (error) {
      console.error("Failed to load contacts:", error);
      // 返回缓存数据
      return this.contacts;
    }
  }

  private parseContactsOutput(output: string): Contact[] {
    const contacts: Contact[] = [];
    const lines = output.trim().split("\n").filter(Boolean);

    for (const line of lines) {
      try {
        const [id, name, nickname, organization, phonesStr, emailsStr] = line.split("|");

        if (!name) continue;

        const phones: Contact["phones"] = [];
        if (phonesStr) {
          const phoneParts = phonesStr.split(";").filter(Boolean);
          for (const part of phoneParts) {
            const [label, number] = part.split(":");
            if (number) {
              phones.push({ label: label || "mobile", number: number.trim() });
            }
          }
        }

        const emails: Contact["emails"] = [];
        if (emailsStr) {
          const emailParts = emailsStr.split(";").filter(Boolean);
          for (const part of emailParts) {
            const [label, address] = part.split(":");
            if (address) {
              emails.push({ label: label || "home", address: address.trim() });
            }
          }
        }

        contacts.push({
          id: id || `contact_${contacts.length}`,
          name: name.trim(),
          nickname: nickname?.trim() || undefined,
          organization: organization?.trim() || undefined,
          phones,
          emails,
        });
      } catch {
        // Skip invalid lines
      }
    }

    return contacts;
  }

  /**
   * 搜索联系人 (支持模糊匹配)
   */
  async search(query: string): Promise<Contact[]> {
    await this.loadContacts();

    const lowerQuery = query.toLowerCase().trim();

    // 精确匹配优先
    const exactMatches = this.contacts.filter(
      (c) =>
        c.name.toLowerCase() === lowerQuery ||
        c.nickname?.toLowerCase() === lowerQuery
    );

    if (exactMatches.length > 0) {
      return exactMatches;
    }

    // 前缀匹配
    const prefixMatches = this.contacts.filter(
      (c) =>
        c.name.toLowerCase().startsWith(lowerQuery) ||
        c.nickname?.toLowerCase().startsWith(lowerQuery)
    );

    if (prefixMatches.length > 0) {
      return prefixMatches;
    }

    // 包含匹配
    const containsMatches = this.contacts.filter(
      (c) =>
        c.name.toLowerCase().includes(lowerQuery) ||
        c.nickname?.toLowerCase().includes(lowerQuery) ||
        c.organization?.toLowerCase().includes(lowerQuery)
    );

    if (containsMatches.length > 0) {
      return containsMatches;
    }

    // 拼音首字母匹配 (简化版，只匹配连续首字母)
    const pinyinMatches = this.contacts.filter((c) => {
      const initials = this.getInitials(c.name);
      return initials.toLowerCase().includes(lowerQuery);
    });

    return pinyinMatches;
  }

  /**
   * 获取名字首字母 (用于拼音匹配)
   */
  private getInitials(name: string): string {
    // 对于中文名字，每个字都是一个首字母
    // 对于英文名字，取每个单词的首字母
    const chars = name.split("");
    const initials: string[] = [];

    for (const char of chars) {
      if (/[\u4e00-\u9fa5]/.test(char)) {
        // 中文字符 - 可以扩展为拼音首字母
        initials.push(char);
      } else if (/[a-zA-Z]/.test(char) && (initials.length === 0 || /\s/.test(chars[chars.indexOf(char) - 1] || ""))) {
        // 英文单词首字母
        initials.push(char);
      }
    }

    return initials.join("");
  }

  /**
   * 根据名字获取联系人
   */
  async getByName(name: string): Promise<Contact | null> {
    const results = await this.search(name);
    return results.length > 0 ? results[0] : null;
  }

  /**
   * 获取所有联系人
   */
  async getAll(): Promise<Contact[]> {
    return this.loadContacts();
  }

  /**
   * 清除缓存
   */
  clearCache(): void {
    this.contacts = [];
    this.lastCacheTime = 0;
    if (existsSync(this.cachePath)) {
      try {
        writeFileSync(this.cachePath, "{}");
      } catch {
        // Ignore
      }
    }
  }
}

// ==================== FaceTime Caller ====================

export class FaceTimeCaller {
  private contactsManager: AppleContactsManager;

  constructor(contactsManager?: AppleContactsManager) {
    this.contactsManager = contactsManager ?? new AppleContactsManager();
  }

  /**
   * 发起 FaceTime 视频通话
   */
  async callVideo(target: string): Promise<CallResult> {
    return this.call(target, "facetime-video");
  }

  /**
   * 发起 FaceTime 音频通话
   */
  async callAudio(target: string): Promise<CallResult> {
    return this.call(target, "facetime-audio");
  }

  /**
   * 发起普通电话 (通过 iPhone Handoff)
   */
  async callPhone(target: string): Promise<CallResult> {
    return this.call(target, "phone");
  }

  /**
   * 智能呼叫 - 根据目标自动选择方式
   */
  async smartCall(nameOrNumber: string, preferVideo = false): Promise<CallResult> {
    // 检查是否是电话号码
    const isPhoneNumber = /^[\d\s\-+()]+$/.test(nameOrNumber.trim());

    if (isPhoneNumber) {
      // 直接呼叫号码
      const method = preferVideo ? "facetime-video" : "facetime-audio";
      return this.call(nameOrNumber, method);
    }

    // 搜索联系人
    const contact = await this.contactsManager.getByName(nameOrNumber);

    if (!contact) {
      return {
        success: false,
        method: "facetime-audio",
        target: nameOrNumber,
        error: `未找到联系人: ${nameOrNumber}`,
      };
    }

    // 优先使用手机号码
    const phone = contact.phones.find((p) =>
      p.label.toLowerCase().includes("mobile") ||
      p.label.toLowerCase().includes("iphone") ||
      p.label.toLowerCase().includes("手机")
    ) ?? contact.phones[0];

    if (phone) {
      const method = preferVideo ? "facetime-video" : "facetime-audio";
      const result = await this.call(phone.number, method);
      result.contactName = contact.name;
      return result;
    }

    // 没有电话号码，尝试邮箱 (FaceTime 可以用 Apple ID 呼叫)
    const email = contact.emails[0];
    if (email) {
      const method = preferVideo ? "facetime-video" : "facetime-audio";
      const result = await this.call(email.address, method);
      result.contactName = contact.name;
      return result;
    }

    return {
      success: false,
      method: "facetime-audio",
      target: nameOrNumber,
      contactName: contact.name,
      error: `联系人 ${contact.name} 没有电话号码或邮箱`,
    };
  }

  /**
   * 执行呼叫
   */
  private async call(
    target: string,
    method: "facetime-video" | "facetime-audio" | "phone"
  ): Promise<CallResult> {
    try {
      // 清理目标字符串
      const cleanTarget = target.replace(/[\s\-()]/g, "");

      let url: string;

      switch (method) {
        case "facetime-video":
          url = `facetime://${encodeURIComponent(cleanTarget)}`;
          break;
        case "facetime-audio":
          url = `facetime-audio://${encodeURIComponent(cleanTarget)}`;
          break;
        case "phone":
          url = `tel://${encodeURIComponent(cleanTarget)}`;
          break;
      }

      // 使用 open 命令打开 URL
      execSync(`open "${url}"`, { encoding: "utf-8" });

      return {
        success: true,
        method,
        target: cleanTarget,
      };
    } catch (error: any) {
      return {
        success: false,
        method,
        target,
        error: error.message ?? String(error),
      };
    }
  }

  /**
   * 获取联系人管理器
   */
  getContactsManager(): AppleContactsManager {
    return this.contactsManager;
  }
}

// ==================== Call Agent ====================

export class CallAgent {
  private caller: FaceTimeCaller;
  private recentCalls: {
    timestamp: number;
    contact: string;
    method: string;
    success: boolean;
  }[] = [];

  constructor() {
    this.caller = new FaceTimeCaller();
  }

  /**
   * 解析自然语言呼叫意图
   */
  parseCallIntent(input: string): {
    action: "call" | "video" | "audio" | "unknown";
    target: string | null;
  } {
    const lowerInput = input.toLowerCase();

    // 检测动作
    let action: "call" | "video" | "audio" | "unknown" = "unknown";

    if (
      lowerInput.includes("视频") ||
      lowerInput.includes("video") ||
      lowerInput.includes("facetime视频")
    ) {
      action = "video";
    } else if (
      lowerInput.includes("打电话") ||
      lowerInput.includes("打给") ||
      lowerInput.includes("呼叫") ||
      lowerInput.includes("call") ||
      lowerInput.includes("拨打") ||
      lowerInput.includes("联系")
    ) {
      action = "call";
    } else if (
      lowerInput.includes("语音") ||
      lowerInput.includes("audio") ||
      lowerInput.includes("facetime")
    ) {
      action = "audio";
    }

    // 提取目标
    let target: string | null = null;

    // 常见模式
    const patterns = [
      /(?:打电话|打给|呼叫|拨打|联系|call|视频|语音)\s*(?:给|to)?\s*(.+)/i,
      /(?:我要|我想|帮我)\s*(?:打电话|打给|呼叫|联系)\s*(?:给)?\s*(.+)/i,
      /(.+)\s*(?:的电话|的视频)/i,
    ];

    for (const pattern of patterns) {
      const match = input.match(pattern);
      if (match && match[1]) {
        target = match[1].trim();
        // 移除末尾的标点符号
        target = target.replace(/[，。！？,.!?]$/, "").trim();
        break;
      }
    }

    return { action, target };
  }

  /**
   * 执行呼叫任务
   */
  async executeCall(input: string): Promise<{
    success: boolean;
    message: string;
    result?: CallResult;
  }> {
    const intent = this.parseCallIntent(input);

    if (intent.action === "unknown") {
      return {
        success: false,
        message: "无法识别呼叫意图。请使用类似 '打电话给张三' 或 '视频呼叫李四' 的格式。",
      };
    }

    if (!intent.target) {
      return {
        success: false,
        message: "请指定要呼叫的联系人或电话号码。",
      };
    }

    // 执行呼叫
    const preferVideo = intent.action === "video";
    const result = await this.caller.smartCall(intent.target, preferVideo);

    // 记录通话
    this.recentCalls.push({
      timestamp: Date.now(),
      contact: result.contactName ?? intent.target,
      method: result.method,
      success: result.success,
    });

    // 保持最近 20 条记录
    if (this.recentCalls.length > 20) {
      this.recentCalls.shift();
    }

    if (result.success) {
      const methodName =
        result.method === "facetime-video" ? "FaceTime 视频" :
        result.method === "facetime-audio" ? "FaceTime 音频" : "电话";

      return {
        success: true,
        message: `正在发起 ${methodName} 呼叫: ${result.contactName ?? result.target}`,
        result,
      };
    } else {
      return {
        success: false,
        message: result.error ?? "呼叫失败",
        result,
      };
    }
  }

  /**
   * 搜索联系人
   */
  async searchContacts(query: string): Promise<Contact[]> {
    return this.caller.getContactsManager().search(query);
  }

  /**
   * 获取最近通话记录
   */
  getRecentCalls(): typeof this.recentCalls {
    return [...this.recentCalls];
  }

  /**
   * 获取 FaceTime Caller
   */
  getCaller(): FaceTimeCaller {
    return this.caller;
  }
}

// ==================== Exports ====================

export function createContactsManager(): AppleContactsManager {
  return new AppleContactsManager();
}

export function createFaceTimeCaller(): FaceTimeCaller {
  return new FaceTimeCaller();
}

export function createCallAgent(): CallAgent {
  return new CallAgent();
}

// 单例
let globalCallAgent: CallAgent | null = null;

export function getCallAgent(): CallAgent {
  if (!globalCallAgent) {
    globalCallAgent = createCallAgent();
  }
  return globalCallAgent;
}
