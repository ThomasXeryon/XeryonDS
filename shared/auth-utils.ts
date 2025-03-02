import { scryptSync, randomBytes, timingSafeEqual } from "crypto";

export function hashPassword(password: string) {
  try {
    const salt = randomBytes(16).toString("hex");
    const hashedBuffer = scryptSync(password, salt, 64);
    const hashedPassword = `${hashedBuffer.toString("hex")}.${salt}`;
    return hashedPassword;
  } catch (error) {
    console.error("Error hashing password:", error);
    throw new Error("Failed to hash password");
  }
}

export function comparePasswords(supplied: string, stored: string) {
  try {
    const [hashedPass, salt] = stored.split(".");
    if (!hashedPass || !salt) {
      console.error("Invalid stored password format");
      return false;
    }

    const hashedSupplied = scryptSync(supplied, salt, 64).toString("hex");
    return hashedPass === hashedSupplied;
  } catch (error) {
    console.error("Error comparing passwords:", error);
    return false;
  }
}