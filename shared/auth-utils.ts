import { scryptSync, randomBytes, timingSafeEqual } from "crypto";

export function hashPassword(password: string) {
  const salt = randomBytes(16).toString("hex");
  const hashedBuffer = scryptSync(password, salt, 64);
  return `${hashedBuffer.toString("hex")}.${salt}`;
}

export function comparePasswords(supplied: string, stored: string) {
  const [hashed, salt] = stored.split(".");
  const hashedBuffer = Buffer.from(hashed, "hex");
  const suppliedBuffer = scryptSync(supplied, salt, 64);
  return timingSafeEqual(hashedBuffer, suppliedBuffer);
}
