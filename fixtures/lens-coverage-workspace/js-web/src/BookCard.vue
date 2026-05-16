<script setup lang="ts">
import { defineProps } from 'vue';

defineProps<{ title: string }>();
</script>

<template>
    <div>
        <router-link to="/books">Back to books</router-link>
    </div>
</template>
