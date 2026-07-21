/**
 * Solar AI OS - Platform Integration Module
 *
 * 平台原生能力集成
 */

// ==================== Apple Shortcuts ====================

export {
  // Types
  type Shortcut,
  type ShortcutRunResult,
  type ShortcutAction,
  type ShortcutDefinition,
  type Platform,

  // Platform detection
  detectPlatform,
  isShortcutsAvailable,

  // Classes
  AppleShortcutsManager,
  SolarShortcutsBridge,

  // Factory functions
  createShortcutsManager,
  createShortcutsBridge,
  getShortcutsManager,
  getShortcutsBridge,
} from "./apple-shortcuts";

// ==================== Apple Contacts & FaceTime ====================

export {
  // Types
  type Contact,
  type CallResult,

  // Classes
  AppleContactsManager,
  FaceTimeCaller,
  CallAgent,

  // Factory functions
  createContactsManager,
  createFaceTimeCaller,
  createCallAgent,
  getCallAgent,
} from "./apple-contacts";
