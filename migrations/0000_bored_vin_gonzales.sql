CREATE TABLE "feedback" (
	"id" serial PRIMARY KEY NOT NULL,
	"user_id" integer,
	"type" text NOT NULL,
	"message" text NOT NULL,
	"created_at" timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "session_logs" (
	"id" serial PRIMARY KEY NOT NULL,
	"station_id" integer,
	"user_id" integer,
	"start_time" timestamp NOT NULL,
	"end_time" timestamp,
	"command_count" integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE "stations" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"rpi_id" text NOT NULL,
	"status" text DEFAULT 'available' NOT NULL,
	"current_user_id" integer,
	"session_start" timestamp,
	"is_active" boolean DEFAULT true NOT NULL,
	"preview_image" text,
	CONSTRAINT "stations_rpi_id_unique" UNIQUE("rpi_id")
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" serial PRIMARY KEY NOT NULL,
	"username" text NOT NULL,
	"password" text NOT NULL,
	"is_admin" boolean DEFAULT false NOT NULL,
	CONSTRAINT "users_username_unique" UNIQUE("username")
);
--> statement-breakpoint
ALTER TABLE "feedback" ADD CONSTRAINT "feedback_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "session_logs" ADD CONSTRAINT "session_logs_station_id_stations_id_fk" FOREIGN KEY ("station_id") REFERENCES "public"."stations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "session_logs" ADD CONSTRAINT "session_logs_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "stations" ADD CONSTRAINT "stations_current_user_id_users_id_fk" FOREIGN KEY ("current_user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;