import { scryptSync, randomBytes, timingSafeEqual } from "crypto";

export function hashPassword(password: string) {
  try {
    const salt = randomBytes(16).toString("hex");
    const hashedBuffer = scryptSync(password, salt, 64);
    const hashedPassword = `${hashedBuffer.toString("hex")}.${salt}`;
    console.log(`Generated password hash with format: ${hashedPassword.split('.').length} parts`);
    return hashedPassword;
  } catch (error) {
    console.error("Error hashing password:", error);
    throw new Error("Failed to hash password");
  }
}

export function comparePasswords(supplied: string, stored: string) {
  try {
    const [hashed, salt] = stored.split(".");
    if (!hashed || !salt) {
      console.error("Invalid stored password format");
      return false;
    }

    const hashedBuffer = Buffer.from(hashed, "hex");
    const suppliedBuffer = scryptSync(supplied, salt, 64);

    console.log(`Comparing password hashes:
    - Stored hash length: ${hashedBuffer.length}
    - Supplied hash length: ${suppliedBuffer.length}`);

    return timingSafeEqual(hashedBuffer, suppliedBuffer);
  } catch (error) {
    console.error("Error comparing passwords:", error);
    return false;
  }
}