import { gql } from 'graphql-tag';

export const typeDefs = gql`
    type Query {
        ping: String!
    }
`;

export const resolvers = {
    Query: {
        ping: () => 'pong',
    },
};
