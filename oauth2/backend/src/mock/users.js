/**
 * The "user pool" for AUTH_MODE=mock.
 *
 * In cognito mode these people live in AWS instead and this file is never
 * loaded. Passwords are here only so the mock login page can be a realistic
 * form; the real Hosted UI obviously never shows you the password.
 */
export const MOCK_USERS = [
  {
    sub: '11111111-1111-4111-8111-111111111111',
    username: 'alice',
    password: 'Password1!',
    email: 'alice@example.com',
    name: 'Alice Adams',
    groups: ['admin'],
  },
  {
    sub: '22222222-2222-4222-8222-222222222222',
    username: 'bob',
    password: 'Password1!',
    email: 'bob@example.com',
    name: 'Bob Brown',
    groups: ['viewer'],
  },
];

export const findMockUser = (username, password) =>
  MOCK_USERS.find(
    (u) => u.username === username && (password === undefined || u.password === password),
  ) ?? null;
