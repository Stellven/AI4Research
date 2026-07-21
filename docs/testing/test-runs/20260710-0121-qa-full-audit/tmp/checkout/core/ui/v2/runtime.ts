/**
 * TUV v2 Runtime
 *
 * Main runtime for Solar AI OS terminal UI
 * Integrates TVS rendering with multi-panel layout
 */

import { LayoutManager } from "./layout-manager";
import { CommandPalette, createSolarCommandPalette } from "./components/command-palette";
import type {
  LayoutPreset,
  PanelId,
  ComponentConfig,
  KeyBinding,
  TUVState,
  Command,
} from "./types";

// ==================== Types ====================

export interface TUVRuntimeConfig {
  layout?: LayoutPreset;
  title?: string;
  refreshInterval?: number;
  commands?: Command[];
  keyBindings?: KeyBinding[];
  onExit?: () => void;
}

export interface PanelContent {
  vdl?: object;
  lines?: string[];
}

// ==================== Default Key Bindings ====================

const DEFAULT_BINDINGS: KeyBinding[] = [
  // Global
  { key: "p", ctrl: true, shift: true, action: "command-palette", scope: "global" },
  { key: "q", ctrl: true, action: "quit", scope: "global" },
  { key: "Escape", action: "close-overlay", scope: "global" },

  // Panel navigation
  { key: "Tab", action: "focus-next", scope: "global" },
  { key: "Tab", shift: true, action: "focus-prev", scope: "global" },
  { key: "1", alt: true, action: "focus-main", scope: "global" },
  { key: "2", alt: true, action: "focus-side", scope: "global" },
  { key: "3", alt: true, action: "focus-bottom", scope: "global" },

  // Panel operations
  { key: "b", ctrl: true, action: "toggle-side", scope: "global" },
  { key: "`", ctrl: true, action: "toggle-bottom", scope: "global" },

  // Layout
  { key: "1", ctrl: true, action: "layout-ide", scope: "global" },
  { key: "2", ctrl: true, action: "layout-dashboard", scope: "global" },
  { key: "3", ctrl: true, action: "layout-focus", scope: "global" },

  // Vim-style navigation (in panels)
  { key: "j", action: "move-down", scope: "main" },
  { key: "k", action: "move-up", scope: "main" },
  { key: "h", action: "move-left", scope: "main" },
  { key: "l", action: "move-right", scope: "main" },
  { key: "g", action: "move-top", scope: "main" },
  { key: "G", shift: true, action: "move-bottom", scope: "main" },

  // Actions
  { key: "Enter", action: "select", scope: "main" },
  { key: " ", action: "toggle", scope: "main" },
];

// ==================== TUV Runtime ====================

export class TUVRuntime {
  private layoutManager: LayoutManager;
  private commandPalette: CommandPalette;
  private config: TUVRuntimeConfig;
  private panelContents: Map<PanelId, PanelContent> = new Map();
  private components: Map<string, ComponentConfig> = new Map();
  private keyBindings: KeyBinding[];
  private running = false;
  private refreshTimer?: NodeJS.Timer;

  constructor(config: TUVRuntimeConfig = {}) {
    this.config = config;
    this.layoutManager = new LayoutManager(config.layout ?? "ide");
    this.commandPalette = createSolarCommandPalette(config.commands);
    this.keyBindings = [...DEFAULT_BINDINGS, ...(config.keyBindings ?? [])];

    // Handle terminal resize
    process.stdout.on("resize", () => {
      const { columns, rows } = process.stdout;
      this.layoutManager.handleResize(columns ?? 120, rows ?? 40);
      this.render();
    });
  }

  // ==================== Lifecycle ====================

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    // Setup terminal
    this.setupTerminal();

    // Initial render
    this.render();

    // Start refresh loop
    if (this.config.refreshInterval) {
      this.refreshTimer = setInterval(() => {
        this.render();
      }, this.config.refreshInterval);
    }

    // Setup input handling
    this.setupInput();
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;

    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
    }

    this.teardownTerminal();
    this.config.onExit?.();
  }

  private setupTerminal(): void {
    // Enable raw mode for key input
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
    }
    process.stdin.resume();

    // Hide cursor
    process.stdout.write("\x1b[?25l");

    // Clear screen
    process.stdout.write("\x1b[2J\x1b[H");

    // Enable alternate screen buffer
    process.stdout.write("\x1b[?1049h");
  }

  private teardownTerminal(): void {
    // Disable alternate screen buffer
    process.stdout.write("\x1b[?1049l");

    // Show cursor
    process.stdout.write("\x1b[?25h");

    // Disable raw mode
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(false);
    }
  }

  private setupInput(): void {
    process.stdin.on("data", (data) => {
      this.handleInput(data.toString());
    });
  }

  // ==================== Input Handling ====================

  private handleInput(input: string): void {
    // Check for command palette input first
    if (this.commandPalette.isVisible()) {
      this.handleCommandPaletteInput(input);
      return;
    }

    // Parse key code
    const key = this.parseKeyCode(input);
    if (!key) return;

    // Find matching binding
    const binding = this.findBinding(key);
    if (binding) {
      this.executeAction(binding.action);
    }
  }

  private handleCommandPaletteInput(input: string): void {
    // Escape closes palette
    if (input === "\x1b") {
      this.commandPalette.close();
      this.render();
      return;
    }

    // Enter executes
    if (input === "\r") {
      this.commandPalette.executeSelected();
      this.render();
      return;
    }

    // Arrow keys
    if (input === "\x1b[A") {
      // Up
      this.commandPalette.selectPrev();
      this.render();
      return;
    }
    if (input === "\x1b[B") {
      // Down
      this.commandPalette.selectNext();
      this.render();
      return;
    }

    // Backspace
    if (input === "\x7f" || input === "\b") {
      this.commandPalette.backspace();
      this.render();
      return;
    }

    // Printable characters
    if (input.length === 1 && input >= " " && input <= "~") {
      this.commandPalette.appendQuery(input);
      this.render();
    }
  }

  private parseKeyCode(input: string): { key: string; ctrl: boolean; alt: boolean; shift: boolean } | null {
    const ctrl = input.charCodeAt(0) < 32;
    const alt = input.startsWith("\x1b") && input.length > 1 && !input.startsWith("\x1b[");

    if (ctrl && !alt) {
      // Ctrl+letter
      const letter = String.fromCharCode(input.charCodeAt(0) + 64).toLowerCase();
      return { key: letter, ctrl: true, alt: false, shift: false };
    }

    if (alt) {
      // Alt+key
      const key = input.slice(1);
      return { key, ctrl: false, alt: true, shift: false };
    }

    // Special keys
    if (input === "\x1b[A") return { key: "ArrowUp", ctrl: false, alt: false, shift: false };
    if (input === "\x1b[B") return { key: "ArrowDown", ctrl: false, alt: false, shift: false };
    if (input === "\x1b[C") return { key: "ArrowRight", ctrl: false, alt: false, shift: false };
    if (input === "\x1b[D") return { key: "ArrowLeft", ctrl: false, alt: false, shift: false };
    if (input === "\t") return { key: "Tab", ctrl: false, alt: false, shift: false };
    if (input === "\x1b[Z") return { key: "Tab", ctrl: false, alt: false, shift: true };
    if (input === "\r") return { key: "Enter", ctrl: false, alt: false, shift: false };
    if (input === "\x1b") return { key: "Escape", ctrl: false, alt: false, shift: false };

    // Regular key
    if (input.length === 1) {
      const isUpperCase = input >= "A" && input <= "Z";
      return {
        key: input.toLowerCase(),
        ctrl: false,
        alt: false,
        shift: isUpperCase,
      };
    }

    return null;
  }

  private findBinding(
    key: { key: string; ctrl: boolean; alt: boolean; shift: boolean }
  ): KeyBinding | null {
    const focusedPanel = this.layoutManager.getFocusedPanel();

    // First check panel-specific bindings
    for (const binding of this.keyBindings) {
      if (binding.scope === focusedPanel || binding.scope === "global") {
        if (
          binding.key.toLowerCase() === key.key &&
          (binding.ctrl ?? false) === key.ctrl &&
          (binding.alt ?? false) === key.alt &&
          (binding.shift ?? false) === key.shift
        ) {
          return binding;
        }
      }
    }

    return null;
  }

  private executeAction(action: string): void {
    switch (action) {
      // Global
      case "command-palette":
        this.commandPalette.toggle();
        break;
      case "quit":
        this.stop();
        break;
      case "close-overlay":
        this.commandPalette.close();
        break;

      // Focus
      case "focus-next":
        this.layoutManager.cycleFocus("next");
        break;
      case "focus-prev":
        this.layoutManager.cycleFocus("prev");
        break;
      case "focus-main":
        this.layoutManager.focusPanel("main");
        break;
      case "focus-side":
        this.layoutManager.focusPanel("side");
        break;
      case "focus-bottom":
        this.layoutManager.focusPanel("bottom");
        break;

      // Toggle
      case "toggle-side":
        this.layoutManager.togglePanel("side");
        break;
      case "toggle-bottom":
        this.layoutManager.togglePanel("bottom");
        break;

      // Layout
      case "layout-ide":
        this.layoutManager.setLayout("ide");
        break;
      case "layout-dashboard":
        this.layoutManager.setLayout("dashboard");
        break;
      case "layout-focus":
        this.layoutManager.setLayout("focus");
        break;

      default:
        // Unknown action - could be custom
        console.log(`Unknown action: ${action}`);
    }

    this.render();
  }

  // ==================== Content Management ====================

  setPanelContent(panelId: PanelId, content: PanelContent): void {
    this.panelContents.set(panelId, content);
    if (this.running) {
      this.render();
    }
  }

  registerComponent(component: ComponentConfig): void {
    this.components.set(component.id, component);
  }

  // ==================== Rendering ====================

  render(): void {
    if (!this.running) return;

    const regions = this.layoutManager.getRenderRegions();
    const state = this.layoutManager.getState();

    // Clear screen
    process.stdout.write("\x1b[H");

    // Render each panel
    this.renderHeader(regions.header, state);
    this.renderPanel("side", regions.side, state);
    this.renderPanel("main", regions.main, state);
    this.renderPanel("bottom", regions.bottom, state);
    this.renderStatusBar(regions.statusbar, state);

    // Render overlays (command palette)
    if (this.commandPalette.isVisible()) {
      this.renderCommandPalette(state);
    }
  }

  private renderHeader(
    region: { x: number; y: number; width: number; height: number },
    state: TUVState
  ): void {
    if (region.height === 0) return;

    const title = this.config.title ?? "☀️ Solar AI OS";
    const time = new Date().toLocaleTimeString();

    const line = ` ${title}${"─".repeat(region.width - title.length - time.length - 4)}${time} `;

    this.moveCursor(region.x, region.y);
    process.stdout.write(`\x1b[7m${line}\x1b[0m`); // Inverse colors
  }

  private renderPanel(
    panelId: PanelId,
    region: { x: number; y: number; width: number; height: number },
    state: TUVState
  ): void {
    if (region.width === 0 || region.height === 0) return;

    const isFocused = state.focus.currentPanel === panelId;
    const content = this.panelContents.get(panelId);
    const borderChar = isFocused ? "║" : "│";
    const cornerTL = isFocused ? "╔" : "┌";
    const cornerTR = isFocused ? "╗" : "┐";
    const cornerBL = isFocused ? "╚" : "└";
    const cornerBR = isFocused ? "╝" : "┘";
    const horizontal = isFocused ? "═" : "─";

    // Top border
    this.moveCursor(region.x, region.y);
    const title = ` ${panelId.toUpperCase()} `;
    const topLine =
      cornerTL +
      horizontal.repeat(2) +
      title +
      horizontal.repeat(region.width - title.length - 4) +
      cornerTR;
    process.stdout.write(isFocused ? `\x1b[33m${topLine}\x1b[0m` : topLine);

    // Content area
    const lines = content?.lines ?? [""];
    for (let i = 0; i < region.height - 2; i++) {
      this.moveCursor(region.x, region.y + i + 1);
      const line = lines[i] ?? "";
      const paddedLine = line.slice(0, region.width - 2).padEnd(region.width - 2);
      const borderColor = isFocused ? "\x1b[33m" : "";
      const reset = isFocused ? "\x1b[0m" : "";
      process.stdout.write(`${borderColor}${borderChar}${reset}${paddedLine}${borderColor}${borderChar}${reset}`);
    }

    // Bottom border
    this.moveCursor(region.x, region.y + region.height - 1);
    const bottomLine = cornerBL + horizontal.repeat(region.width - 2) + cornerBR;
    process.stdout.write(isFocused ? `\x1b[33m${bottomLine}\x1b[0m` : bottomLine);
  }

  private renderStatusBar(
    region: { x: number; y: number; width: number; height: number },
    state: TUVState
  ): void {
    if (region.height === 0) return;

    const layout = `Layout: ${state.layout.preset}`;
    const focus = `Focus: ${state.focus.currentPanel}`;
    const help = "Ctrl+Shift+P: Commands | Ctrl+Q: Quit";

    const line = ` ${layout} │ ${focus} │ ${help}`.padEnd(region.width);

    this.moveCursor(region.x, region.y);
    process.stdout.write(`\x1b[100m${line}\x1b[0m`); // Gray background
  }

  private renderCommandPalette(state: TUVState): void {
    const lines = this.commandPalette.render(60);
    const startX = Math.floor((state.width - 60) / 2);
    const startY = 3;

    for (let i = 0; i < lines.length; i++) {
      this.moveCursor(startX, startY + i);
      process.stdout.write(`\x1b[44m\x1b[97m${lines[i]}\x1b[0m`); // Blue background, white text
    }
  }

  private moveCursor(x: number, y: number): void {
    process.stdout.write(`\x1b[${y + 1};${x + 1}H`);
  }

  // ==================== State Access ====================

  getState(): TUVState {
    return this.layoutManager.getState();
  }

  getLayoutManager(): LayoutManager {
    return this.layoutManager;
  }

  getCommandPalette(): CommandPalette {
    return this.commandPalette;
  }
}

// ==================== Factory ====================

export function createTUVRuntime(config?: TUVRuntimeConfig): TUVRuntime {
  return new TUVRuntime(config);
}
