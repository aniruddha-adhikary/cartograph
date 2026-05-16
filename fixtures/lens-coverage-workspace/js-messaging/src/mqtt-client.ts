import mqtt from 'mqtt';

const client = mqtt.connect('mqtts://broker.example.com:8883');

client.publish('sensors/temperature', '21.5');
client.subscribe('sensors/temperature');
