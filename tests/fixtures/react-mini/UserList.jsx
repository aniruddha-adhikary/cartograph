import React from 'react';

function UserCard({ user }) {
  return <div className="card">{user.name}</div>;
}

function UserList() {
  const load = () => fetch('/api/users');
  return <UserCard />;
}

class App extends React.Component {
  render() {
    return <UserList />;
  }
}
