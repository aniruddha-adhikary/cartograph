<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
    name: 'BookList',
    props: { books: Array },
});
</script>

<template>
    <ul>
        <router-link to="/books/new">Create</router-link>
    </ul>
</template>
