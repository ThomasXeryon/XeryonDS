import { pgTable, text, serial, integer, boolean, timestamp } from "drizzle-orm/pg-core";
import { sql as drizzleSql } from "drizzle-orm";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const users = pgTable("users", {
  id: serial("id").primaryKey(),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
  isAdmin: boolean("is_admin").notNull().default(false),
});

export const stations = pgTable("stations", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  rpiId: text("rpi_id").notNull().unique(),
  status: text("status").notNull().default("available"),
  currentUserId: integer("current_user_id").references(() => users.id),
  sessionStart: timestamp("session_start"),
  isActive: boolean("is_active").notNull().default(true),
  previewImage: text("preview_image"),
});

export const sessionLogs = pgTable("session_logs", {
  id: serial("id").primaryKey(),
  stationId: integer("station_id").references(() => stations.id),
  userId: integer("user_id").references(() => users.id),
  startTime: timestamp("start_time").notNull(),
  endTime: timestamp("end_time"),
  commandCount: integer("command_count").notNull().default(0),
});

export const feedback = pgTable("feedback", {
  id: serial("id").primaryKey(),
  userId: integer("user_id").references(() => users.id),
  type: text("type").notNull(),
  message: text("message").notNull(),
  createdAt: timestamp("created_at").notNull().default(drizzleSql`CURRENT_TIMESTAMP`),
  status: text("status").notNull().default("pending"),
});

export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

export const insertStationSchema = createInsertSchema(stations).pick({
  name: true,
  rpiId: true,
});

export const insertFeedbackSchema = createInsertSchema(feedback)
  .pick({
    type: true,
    message: true,
  })
  .extend({
    type: z.enum(["feedback", "bug"]),
  });

export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof users.$inferSelect;
export type Station = typeof stations.$inferSelect;
export type SessionLog = typeof sessionLogs.$inferSelect;
export type Feedback = typeof feedback.$inferSelect;
export type InsertFeedback = z.infer<typeof insertFeedbackSchema>;

export type WebSocketMessage = {
  type: "move" | "stop" | "step" | "scan" | "speed" | "demo_start" | "demo_stop";
  direction?: "up" | "down" | "left" | "right";
  value?: number;
  stationId: number;
  rpiId: string;
  command: string;
};

export type RPiResponse = {
  type: "rpi_response" | "error" | "rpi_list" | "command_sent";
  rpiId?: string;
  message?: string;
  status?: string;
  rpiIds?: string[];
};