import React from 'react';

function UserList() {
  const loadUsers = () => fetch('/api/users');
  const createUser = (data) => fetch('/api/users', { method: 'POST' });
  return <div onClick={loadUsers}>users</div>;
}
