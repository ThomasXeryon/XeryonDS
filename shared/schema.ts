import { pgTable, text, serial, integer, boolean, timestamp, jsonb, doublePrecision, real } from "drizzle-orm/pg-core";
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

// For position data recording during sessions
export const positionData = pgTable("position_data", {
  id: serial("id").primaryKey(),
  sessionLogId: integer("session_log_id").references(() => sessionLogs.id),
  timestamp: timestamp("timestamp").notNull().default(drizzleSql`CURRENT_TIMESTAMP`),
  position: real("position").notNull(),
  // Store command info when position change is due to a command
  commandType: text("command_type"),
  commandDirection: text("command_direction"),
  commandStepSize: real("command_step_size"),
  commandStepUnit: text("command_step_unit"),
});

// For recording commands during sessions
export const commandLogs = pgTable("command_logs", {
  id: serial("id").primaryKey(),
  sessionLogId: integer("session_log_id").references(() => sessionLogs.id),
  timestamp: timestamp("timestamp").notNull().default(drizzleSql`CURRENT_TIMESTAMP`),
  command: text("command").notNull(),
  direction: text("direction"),
  stepSize: real("step_size"),
  stepUnit: text("step_unit"),
  parameters: jsonb("parameters"),
});

// For system health monitoring
export const systemHealth = pgTable("system_health", {
  id: serial("id").primaryKey(),
  timestamp: timestamp("timestamp").notNull().default(drizzleSql`CURRENT_TIMESTAMP`),
  stationId: integer("station_id").references(() => stations.id),
  status: text("status").notNull(),
  connectionLatency: integer("connection_latency"),  // in milliseconds
  cpuUsage: real("cpu_usage"),  // percentage
  memoryUsage: real("memory_usage"),  // percentage
  uptimeSeconds: integer("uptime_seconds"),
  details: jsonb("details"),  // for additional health metrics
});

// For technical specifications of each station
export const technicalSpecs = pgTable("technical_specs", {
  id: serial("id").primaryKey(),
  stationId: integer("station_id").references(() => stations.id).notNull().unique(),
  actuatorModel: text("actuator_model").notNull(),
  resolution: real("resolution").notNull(), // in μm
  travelRange: real("travel_range").notNull(), // in mm
  maxSpeed: real("max_speed").notNull(), // in mm/s
  maxAcceleration: real("max_acceleration"), // in mm/s²
  minStepSize: real("min_step_size").notNull(), // in μm
  repeatability: real("repeatability"), // in μm
  straightness: real("straightness"), // in μm
  flatness: real("flatness"), // in μm
  additionalSpecs: jsonb("additional_specs"), // JSON field for other specifications
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

// Types for the new tables
export type PositionDataPoint = typeof positionData.$inferSelect;
export type CommandLog = typeof commandLogs.$inferSelect;
export type SystemHealthStatus = typeof systemHealth.$inferSelect;
export type TechnicalSpec = typeof technicalSpecs.$inferSelect;

// Schema for technical specs insertion
export const insertTechSpecsSchema = createInsertSchema(technicalSpecs)
  .pick({
    stationId: true,
    actuatorModel: true,
    resolution: true,
    travelRange: true,
    maxSpeed: true,
    minStepSize: true,
    maxAcceleration: true,
    repeatability: true,
    straightness: true,
    flatness: true,
  });

export type InsertTechSpecs = z.infer<typeof insertTechSpecsSchema>;

export type WebSocketMessage = {
  type: "move" | "stop" | "step" | "scan" | "speed" | "demo_start" | "demo_stop" | "home";
  direction?: "up" | "down" | "left" | "right";
  value?: number;
  stationId: number;
  rpiId: string;
  command: string;
  stepSize?: number;
  stepUnit?: string;
};

export type RPiResponse = {
  type: "rpi_response" | "error" | "rpi_list" | "command_sent";
  rpiId?: string;
  message?: string;
  status?: string;
  rpiIds?: string[];
};