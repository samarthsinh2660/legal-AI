/** Auth types the route guards need as well as the auth feature. */

export type Credentials = {
  email: string;
  password: string;
  /** Sign-up only. Absent on sign-in, where the stored name is authoritative. */
  name?: string;
};
