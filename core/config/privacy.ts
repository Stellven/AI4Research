// Compatibility implementation — pending upstream original.
// Absent from the public extraction but imported by reply/security/listener
// surfaces. Env-backed values with neutral fallbacks only; do not extend
// beyond what the daemon needs to boot and serve. See AGENTS.md
// "Compatibility Modules".

function splitList(value: string | undefined): string[] {
  return (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function getFromEmail(): string {
  return process.env.SOLAR_FROM_EMAIL || process.env.EMAIL_FROM || "solar@example.invalid";
}

export function getNotificationEmail(): string {
  return process.env.SOLAR_NOTIFICATION_EMAIL || process.env.NOTIFICATION_EMAIL || getFromEmail();
}

export function getGuardianEmails(): string[] {
  return splitList(process.env.SOLAR_GUARDIAN_EMAILS || process.env.GUARDIAN_EMAILS);
}

export function getGuardianImessageHandle(): string {
  return process.env.SOLAR_GUARDIAN_IMESSAGE || process.env.GUARDIAN_IMESSAGE || "";
}

export function getGuardianIdentifiers(): string[] {
  const values = [
    ...getGuardianEmails(),
    getGuardianImessageHandle(),
    process.env.SOLAR_GUARDIAN_TELEGRAM || "",
  ];
  return values.map((item) => item.trim()).filter(Boolean);
}
