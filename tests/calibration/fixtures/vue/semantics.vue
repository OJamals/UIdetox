<script setup lang="ts">
import { ref } from "vue";
const open = ref(false);
</script>

<template>
  <section data-testid="panel">
    <button @click="open = true">Open</button>
  </section>
</template>
