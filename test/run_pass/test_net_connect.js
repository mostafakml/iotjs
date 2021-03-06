/* Copyright 2017-present Samsung Electronics Co., Ltd. and other contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

var assert = require('assert');
var net = require('net');
var host = '127.0.0.1';
var port = 5696;
var msg = 'Hello IoT.js';

var server = net.createServer({
    allowHalfOpen: true,
  },
  function(socket) {
    server.close();
  }
);

server.listen(port);

server.on('connection', function(socket) {
  var data = '';
  socket.on('data', function(chuck) {
    data += chuck;
  });
  socket.on('end', function() {
    socket.end(data);
  });
});

var socket = net.connect(port, host, function() {
  var data = '';
  socket.on('data', function(chuck) {
    data += chuck;
  });

  socket.on('end', function() {
    assert.equal(data, msg);
  });

  socket.end(msg);
});
