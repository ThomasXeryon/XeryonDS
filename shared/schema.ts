import { pgTable, text, serial, boolean } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";

export const users = pgTable("users", {
  id: serial("id").primaryKey(),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
  isAdmin: boolean("is_admin").notNull().default(false),
});

export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

// Simple station schema
export type Station = {
  id: number;
  name: string;
  status: "available" | "in_use";
  currentSession?: {
    userId: number;
    startTime: string;
  };
};

export type InsertUser = typeof insertUserSchema._type;
export type User = typeof users.$inferSelect;