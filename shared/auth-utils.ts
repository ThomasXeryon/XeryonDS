import { scryptSync, randomBytes, timingSafeEqual } from "crypto";

export function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  const hashedBuffer = scryptSync(password, salt, 64);
  return `${hashedBuffer.toString("hex")}.${salt}`;
}

export function comparePasswords(supplied: string, stored: string) {
  try {
    const [hashedPassword, salt] = stored.split(".");
    if (!hashedPassword || !salt) {
      return false;
    }
    const suppliedHash = scryptSync(supplied, salt, 64).toString("hex");
    return suppliedHash === hashedPassword;
  } catch (error) {
    console.error("Error comparing passwords:", error);
    return false;
  }
}