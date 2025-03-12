
import { eq } from 'drizzle-orm';
import { db } from './db';
import { users, User } from '@shared/schema';

// Create a storage object to export
export const storage = {
  sessionStore: null,

  // User related methods
  async getUser(id: number) {
    if (!id) return null;
    const result = await db.select().from(users).where(eq(users.id, id));
    return result[0] || null;
  },
  
  async getUserByUsername(username: string) {
    if (!username) return null;
    const result = await db.select().from(users).where(eq(users.username, username));
    return result[0] || null;
  },
  
  async createUser(user: {
    username: string;
    password: string;
  }): Promise<User> {
    const result = await db
      .insert(users)
      .values(user)
      .returning({ id: users.id, username: users.username, isAdmin: users.isAdmin });

    return result[0];
  },

  async updateUserAdmin(userId: number, isAdmin: boolean): Promise<void> {
    await db
      .update(users)
      .set({ isAdmin })
      .where(eq(users.id, userId));
  },
};
